// ********************* Includes *********************
#include "config.h"

#include "drivers/pwm.h"
#include "drivers/usb.h"
#include "drivers/gmlan_alt.h"
#include "drivers/kline_init.h"

#include "early_init.h"
#include "provision.h"

#include "power_saving.h"
#include "safety.h"

#include "drivers/can_common.h"

#ifdef STM32H7
  #include "drivers/fdcan.h"
#else
  #include "drivers/bxcan.h"
#endif

#include "obj/gitversion.h"

#include "usb_comms.h"


// ********************* Serial debugging *********************

bool check_started(void) {
  return current_board->check_ignition() || ignition_can;
}

void debug_ring_callback(uart_ring *ring) {
  char rcv;
  while (getc(ring, &rcv)) {
    (void)putc(ring, rcv);  // misra-c2012-17.7: cast to void is ok: debug function

    // only allow bootloader entry on debug builds
    #ifdef ALLOW_DEBUG
      // jump to DFU flash
      if (rcv == 'z') {
        enter_bootloader_mode = ENTER_BOOTLOADER_MAGIC;
        NVIC_SystemReset();
      }
    #endif

    // normal reset
    if (rcv == 'x') {
      NVIC_SystemReset();
    }

    // enable CDP mode
    if (rcv == 'C') {
      puts("switching USB to CDP mode\n");
      current_board->set_usb_power_mode(USB_POWER_CDP);
    }
    if (rcv == 'c') {
      puts("switching USB to client mode\n");
      current_board->set_usb_power_mode(USB_POWER_CLIENT);
    }
    if (rcv == 'D') {
      puts("switching USB to DCP mode\n");
      current_board->set_usb_power_mode(USB_POWER_DCP);
    }
  }
}

// ****************************** safety mode ******************************

// this is the only way to leave silent mode
void set_safety_mode(uint16_t mode, int16_t param) {
  uint16_t mode_copy = mode;
  int err = set_safety_hooks(mode_copy, param);
  if (err == -1) {
    puts("Error: safety set mode failed. Falling back to SILENT\n");
    mode_copy = SAFETY_SILENT;
    err = set_safety_hooks(mode_copy, 0);
    if (err == -1) {
      puts("Error: Failed setting SILENT mode. Hanging\n");
      while (true) {
        // TERMINAL ERROR: we can't continue if SILENT safety mode isn't succesfully set
      }
    }
  }
  blocked_msg_cnt = 0;

  switch (mode_copy) {
    case SAFETY_SILENT:
      set_intercept_relay(false);
      if (current_board->has_obd) {
        current_board->set_can_mode(CAN_MODE_NORMAL);
      }
      can_silent = ALL_CAN_SILENT;
      break;
    case SAFETY_NOOUTPUT:
      set_intercept_relay(false);
      if (current_board->has_obd) {
        current_board->set_can_mode(CAN_MODE_NORMAL);
      }
      can_silent = ALL_CAN_LIVE;
      break;
    case SAFETY_ELM327:
      set_intercept_relay(false);
      heartbeat_counter = 0U;
      heartbeat_lost = false;
      if (current_board->has_obd) {
        if (param == 0) {
          current_board->set_can_mode(CAN_MODE_OBD_CAN2);
        } else {
          current_board->set_can_mode(CAN_MODE_NORMAL);
        }
      }
      can_silent = ALL_CAN_LIVE;
      break;
    default:
      set_intercept_relay(true);
      heartbeat_counter = 0U;
      heartbeat_lost = false;
      if (current_board->has_obd) {
        current_board->set_can_mode(CAN_MODE_NORMAL);
      }
      can_silent = ALL_CAN_LIVE;
      break;
  }
  can_init_all();
}

bool is_car_safety_mode(uint16_t mode) {
  return (mode != SAFETY_SILENT) &&
         (mode != SAFETY_NOOUTPUT) &&
         (mode != SAFETY_ELM327);
}

// ***************************** main code *****************************

// cppcheck-suppress unusedFunction ; used in headers not included in cppcheck
void __initialize_hardware_early(void) {
  early_initialization();
}

void __attribute__ ((noinline)) enable_fpu(void) {
  // enable the FPU
  SCB->CPACR |= ((3UL << (10U * 2U)) | (3UL << (11U * 2U)));
}

// go into SILENT when heartbeat isn't received for this amount of seconds.
#define HEARTBEAT_IGNITION_CNT_ON 5U
#define HEARTBEAT_IGNITION_CNT_OFF 2U

// called at 8Hz
uint8_t loop_counter = 0U;
void tick_handler(void) {
  if (TICK_TIMER->SR != 0) {
    // siren
    current_board->set_siren((loop_counter & 1U) && (siren_enabled || (siren_countdown > 0U)));

    // decimated to 1Hz
    if (loop_counter == 0U) {
      can_live = pending_can_live;

      current_board->usb_power_mode_tick(uptime_cnt);

      //puth(usart1_dma); puts(" "); puth(DMA2_Stream5->M0AR); puts(" "); puth(DMA2_Stream5->NDTR); puts("\n");

      // reset this every 16th pass
      if ((uptime_cnt & 0xFU) == 0U) {
        pending_can_live = 0;
      }
      #ifdef DEBUG
        puts("** blink ");
        puts("rx:"); puth4(can_rx_q.r_ptr); puts("-"); puth4(can_rx_q.w_ptr); puts("  ");
        puts("tx1:"); puth4(can_tx1_q.r_ptr); puts("-"); puth4(can_tx1_q.w_ptr); puts("  ");
        puts("tx2:"); puth4(can_tx2_q.r_ptr); puts("-"); puth4(can_tx2_q.w_ptr); puts("  ");
        puts("tx3:"); puth4(can_tx3_q.r_ptr); puts("-"); puth4(can_tx3_q.w_ptr); puts("\n");
      #endif

      // Tick drivers
      fan_tick();

      // set green LED to be controls allowed
      current_board->set_led(LED_GREEN, controls_allowed | green_led_enabled);

      // turn off the blue LED, turned on by CAN
      // unless we are in power saving mode
      current_board->set_led(LED_BLUE, (uptime_cnt & 1U) && (power_save_status == POWER_SAVE_STATUS_ENABLED));

      // increase heartbeat counter and cap it at the uint32 limit
      if (heartbeat_counter < __UINT32_MAX__) {
        heartbeat_counter += 1U;
      }

      if (siren_countdown > 0U) {
        siren_countdown -= 1U;
      }

      if (controls_allowed) {
        controls_allowed_countdown = 30U;
      } else if (controls_allowed_countdown > 0U) {
        controls_allowed_countdown -= 1U;
      } else {

      }

      // exit controls allowed if unused by openpilot for a few seconds
      if (controls_allowed && !heartbeat_engaged) {
        heartbeat_engaged_mismatches += 1U;
        if (heartbeat_engaged_mismatches >= 3U) {
          controls_allowed = 0U;
        }
      } else {
        heartbeat_engaged_mismatches = 0U;
      }

      if (!heartbeat_disabled) {
        // if the heartbeat has been gone for a while, go to SILENT safety mode and enter power save
        if (heartbeat_counter >= (check_started() ? HEARTBEAT_IGNITION_CNT_ON : HEARTBEAT_IGNITION_CNT_OFF)) {
          puts("device hasn't sent a heartbeat for 0x");
          puth(heartbeat_counter);
          puts(" seconds. Safety is set to SILENT mode.\n");

          if (controls_allowed_countdown > 0U) {
            siren_countdown = 5U;
            controls_allowed_countdown = 0U;
          }

          // set flag to indicate the heartbeat was lost
          if (is_car_safety_mode(current_safety_mode)) {
            heartbeat_lost = true;
          }

          if (current_safety_mode != SAFETY_SILENT) {
            set_safety_mode(SAFETY_SILENT, 0U);
          }
          if (power_save_status != POWER_SAVE_STATUS_ENABLED) {
            set_power_save_state(POWER_SAVE_STATUS_ENABLED);
          }

          // Also disable IR when the heartbeat goes missing
          current_board->set_ir_power(0U);

          // If enumerated but no heartbeat (phone up, boardd not running), turn the fan on to cool the device
          if(usb_enumerated){
            current_board->set_fan_power(50U);
          } else {
            current_board->set_fan_power(0U);
          }
        }

        // enter CDP mode when car starts to ensure we are charging a turned off EON
        if (check_started() && (usb_power_mode != USB_POWER_CDP)) {
          current_board->set_usb_power_mode(USB_POWER_CDP);
        }
      }

      // check registers
      check_registers();

      // set ignition_can to false after 2s of no CAN seen
      if (ignition_can_cnt > 2U) {
        ignition_can = false;
      }

      // on to the next one
      uptime_cnt += 1U;
      safety_mode_cnt += 1U;
      ignition_can_cnt += 1U;

      // synchronous safety check
      safety_tick(current_rx_checks);
    }

    loop_counter++;
    loop_counter %= 8U;
  }
  TICK_TIMER->SR = 0;
}


int main(void) {
  // Init interrupt table
  init_interrupts(true);

  // shouldn't have interrupts here, but just in case
  disable_interrupts();

  // init early devices
  clock_init();
  peripherals_init();
  detect_external_debug_serial();
  detect_board_type();
  adc_init();

  // print hello
  puts("\n\n\n************************ MAIN START ************************\n");

  // check for non-supported board types
  if(hw_type == HW_TYPE_UNKNOWN){
    puts("Unsupported board type\n");
    while (1) { /* hang */ }
  }

  puts("Config:\n");
  puts("  Board type: "); puts(current_board->board_type); puts("\n");
  puts(has_external_debug_serial ? "  Real serial\n" : "  USB serial\n");

  // init board
  current_board->init();

  // panda has an FPU, let's use it!
  enable_fpu();

  // enable main uart if it's connected
  if (has_external_debug_serial) {
    // WEIRDNESS: without this gate around the UART, it would "crash", but only if the ESP is enabled
    // assuming it's because the lines were left floating and spurious noise was on them
    uart_init(&uart_ring_debug, 115200);
  }

  if (current_board->has_gps) {
    uart_init(&uart_ring_gps, 9600);
  } else {
    // enable ESP uart
    uart_init(&uart_ring_gps, 115200);
  }

  if(current_board->has_lin){
    // enable LIN
    uart_init(&uart_ring_lin1, 10400);
    UART5->CR2 |= USART_CR2_LINEN;
    uart_init(&uart_ring_lin2, 10400);
    USART3->CR2 |= USART_CR2_LINEN;
  }

  microsecond_timer_init();

  // init to SILENT and can silent
  set_safety_mode(SAFETY_SILENT, 0);

  // enable CAN TXs
  current_board->enable_can_transceivers(true);

  // 8Hz timer
  REGISTER_INTERRUPT(TICK_TIMER_IRQ, tick_handler, 10U, FAULT_INTERRUPT_RATE_TICK)
  tick_timer_init();

#ifdef DEBUG
  puts("DEBUG ENABLED\n");
#endif
  // enable USB (right before interrupts or enum can fail!)
  usb_init();

  puts("**** INTERRUPTS ON ****\n");
  enable_interrupts();

  // LED should keep on blinking all the time
  uint64_t cnt = 0;

  for (cnt=0;;cnt++) {
    if (power_save_status == POWER_SAVE_STATUS_DISABLED) {
      #ifdef DEBUG_FAULTS
      if(fault_status == FAULT_STATUS_NONE){
      #endif
        uint32_t div_mode = ((usb_power_mode == USB_POWER_DCP) ? 4U : 1U);

        // useful for debugging, fade breaks = panda is overloaded
        for(uint32_t fade = 0U; fade < MAX_LED_FADE; fade += div_mode){
          current_board->set_led(LED_RED, true);
          delay(fade >> 4);
          current_board->set_led(LED_RED, false);
          delay((MAX_LED_FADE - fade) >> 4);
        }

        for(uint32_t fade = MAX_LED_FADE; fade > 0U; fade -= div_mode){
          current_board->set_led(LED_RED, true);
          delay(fade >> 4);
          current_board->set_led(LED_RED, false);
          delay((MAX_LED_FADE - fade) >> 4);
        }

      #ifdef DEBUG_FAULTS
      } else {
          current_board->set_led(LED_RED, 1);
          delay(512000U);
          current_board->set_led(LED_RED, 0);
          delay(512000U);
        }
      #endif
    } else {
      __WFI();
    }
  }

  return 0;
}
