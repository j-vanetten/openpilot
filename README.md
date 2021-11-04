# jvePilot Hybrid OpenPilot/ACC for Chrysler/Jeep 
This fork is only for Chrysler/Jeep vehicles!

[![Buy me a beer!](https://github.com/j-vanetten/openpilot/blob/jvePilot-release/.github/ButMeABeer.png?raw=true)](https://www.buymeacoffee.com/jvePilot)

# Table of contents
- [**Safety Notes**](#safety-notes)
- [jvePilot](#jvepilot)
  * [What is this Fork?](#what-is-this-fork)
  * [Benefits of jvePilot](#benefits-of-jvepilot)
    + [Longitudinal control](#longitudinal-control)
    + [Auto Resume](#auto-resume)
    + [Auto Follow](#auto-follow)
    + [ACC Eco](#acc-eco)
  * [How to use it](#how-to-use-it)
    + [Where to look when setting ACC speed](#where-to-look-when-setting-acc-speed)
- [Install](#install)
  * [Branches](#branches)
- [Customizing](#customizing)
- [Advanced](#advanced-settings)

# **Safety Notes**
* This is my experimental branch, so I'm not responsible for any damage this may cause.
* jvePilot still does not have direct control of the gas and brakes!
  Changing the ACC speed does not always result in the vehicle braking unless the difference in speed is large enough.
  If the speed difference is small, the vehicle just lets off the gas.
* ACC can't go slower that 20mph
* ACC doesn't do a good job at seeing things that are already stopped

---

# jvePilot 
I have a 2018 Grand Cherokee Trailhawk, so I'm only able to confirm features using this vehicle.
* 2017 Gas Chrysler Pacifica: Confirmed by @debugged-hosting

## What is this Fork?
This is my personal OpenPilot fork that includes features that I feel make it a better driving experience for me and possibly others.

## Benefits of jvePilot
* Smother driving in traffic as jvePilot will do a better job at predicting traffic and adjust ACC speed accordingly
* ACC braking by setting the cruse speed lower that the target to help slow the vehicle sooner
* Slow for cars cutting in before ACC does
* Slow in a turn, so you don't have to change the set speed yourself (Speeds are configurable)
* Auto resume after ACC comes to a stop behind vehicle (Can be disabled)
* Auto follow feature to adjust the follow distance based on speed (Speeds are configurable)
* ACC Eco to limit the throttle when accelerating  
* Pressing the gas does not disengage jvePilot (Can be disabled)
* Syncs jvePilot display speed with the vehicle speedometer 
* Use LKAS button in the dash to disable lane line driving and instead use the new KL driving model. [Read about KL model here](https://blog.comma.ai/end-to-end-lateral-planning).
* Gas/brake indication using green/red colors on speed indicator

### Longitudinal control
This fork combines the speed control logic of OpenPilot with the vehicles Adaptive Cruse Control (ACC).
It does this by changing the ACC speed to match the value OpenPilot calculates as the desired speed.
This brings some of OpenPilots longitudinal control to these vehicles.
Including things like slowing while cornering and slowing when it detects cut-ins.
It will also smooth the braking of ACC when driving in traffic.

On FCA vehicles, only the steering is controlled by jvePilot and speed is left up to the ACC of the vehicle.
This fork takes control of the ACC speed setting and adjusts the ACC speed to match the speed jvePilot would be targeting if it actually was able to control the gas and brakes.
It does this by simulating ACC+ and ACC- button presses on the steering wheel to change the ACC speed.
It is limited as ACC only goes down to 20 mph, so it doesn't help as low speeds.

### Auto Resume
ACC will come to a stop behind vehicles, however, if stopped too long, it will either stay stopped until resume is pressed, or simply disengage ACC altogether.  
For the case where ACC simply cancels, the driver has to press and hold the brake to keep the vehicle stopped.
Auto resume makes life easier by resuming ACC when the vehicle in front of you begin to move, or, you let off the brake after coming to a standstill.
While stopped, you can still disengage jvePilot by pressing the Cancel button. 

### Auto Follow
Auto Follow is a way to automate the changing of the stock follow distance setting.
It sets the follow distance to closer at slow speeds and increases it the faster you go.
Setting the follow speed to one/two bars helps with keeping up with cars that take off when stopped or at slow speeds.
The faster you go, the more distance you want, so you can have more confidence in ACC being able to stop in case it needs to.

The current enabled state of Auto Follow is displayed on the bottom of the jvePilot display.
Pressing Follow + or - will disable Auto Follow giving you full control to set the follow distance. 
To re-enable Auto Follow, hold either Follow + or - for half a second or tap the button on the display. 
 
### ACC Eco
When enabled, jvePilot will limit how far ahead the ACC setting is above the current speed.  
This prevents the vehicle from using an aggressive throttle to get up to speed saving on gas/battery.

The ACC Eco button is located in the lower right corner of the display.  
Tapping the button cycles between off, level 1, and level 2 eco settings.
Level 2 provides the slowest acceleration and is selected when both leaves are green.    
Level 1 should provide a balance is selected when only one leaf is green.
If you feel these settings are not right for you or your vehicle, see the [ACC Eco](#acc-eco) setting to adjust them. 
Much like your vehicles eco/sport modes, the current setting is persisted between drives.

## How to use it 
When using this branch, you will be setting the max ACC speed on the jvePilot display instead of the one in the dashboard.
jvePilot will then set the ACC setting in the dashboard to the targeted speed, but never exceeding the max speed set on the jvePilot display.
A quick press of the ACC+ and ACC- buttons will change this speed by 5 mph on the jvePilot display, while a long deliberate press (about a 1/2 second press) changes it by 1 mph.
DO NOT hold the ACC+ or ACC- buttons for longer that a 1 second. Either make quick or long deliberate presses only.

### Where to look when setting ACC speed
Do not look at the dashboard when setting your ACC max speed.
Instead, only look at the one on the jvePilot display.
The reason you need to look at jvePilot is because jvePilot will be changing the one in the dashboard.
It will be adjusting it as needed, never raising it above the one set on the jvePilot display.

**ONLY look at the MAX speed on jvePilot when setting the ACC speed instead of the dashboard!**

---

# Install
The easiest way to install jvePilot is to factory reset and use this Custom Software URL: `https://bit.ly/jvePilot-release`

## Branches
`/jvePilot-release` - The latest release.  Will contain the latest version I feel is ready for daily use. Custom Software URL: `https://bit.ly/jvePilot-release`

`/jvePilot-beta` - Sometimes I have people wanting to beta test jvePilot's new features.  Mostly stable, but still can be buggy. Custom Software URL: `https://bit.ly/jvePilot-beta` 

`/feature/*` - These branches are where I'm working on new features.  These are never safe to run as they change all the time.

---
# Customizing
Customizing features and parameters can be done on the UI display.  
Click the gear icon and then select jvePilot from the sidebar.  
Clicking on the text of feature of will show more information about it and allow customization of the feature.
Note that some settings do require a vehicle restart, and some don't 
The settings that don't require a restart may take upward of 5 seconds to take effect after changing them. 


## Slow in Curves
jvePilot will slow in curves so that you don't have to.
* Default: On
* Vehicle Restart Required: No
### Speed Ratio 
Use this to tune the speed in curves to you liking.
Setting this to 1.2 will cause jvePilot to drive 20% faster in turns than if it was set to the default of 1.0
* Default: 1.0
* Units: Ratio
* Vehicle Restart Required: No
* Min/Max values (0.1, 2)
### Drop off
Adjusts how much the speed drops as the curve increases.
Decrease this value to lessen the amount of drop off as the curve increases.
Changing this value will likely require adjusting the Speed Ratio to compensate.
* Default: 2.0
* Vehicle Restart Required: No
* Min/Max values (1.0, 3.0)

## Reverse ACC +/- Speeds
Reverse the stock ACC +/- button's 1mph on short press and 5mph on long press.  Turn off to return to stock style.
* Default: On
* Vehicle Restart Required: Yes

## Auto Resume
This feature allows jvePilot to auto resume from an ACC stop.
* Default: On
* Vehicle Restart Required: Yes

## Disable on Gas
When enabled, jvePilot will disengage when you press the gas
* Default: Off
* Vehicle Restart Required: Yes

## Auto Follow
If you don't want auto follow enabled on every start, turn this off.
### 1-2 Bar Change Over
When your speed (in MPH) is below this setting, Auto Follow will set the follow setting to one bar.  
When you reach this speed (in MPH), Auto Follow will set the follow setting to two bars.
* Default: 15
* Units: MPH
* Vehicle Restart Required: No
* Min/Max values (0, 300)
### 2-3 Bar Change Over
When your speed (in MPH) is below this setting, Auto Follow will set the follow setting to two bars.
When you reach this speed (in MPH), Auto Follow will set the follow setting to three bars.
* Default: 30
* Units: MPH
* Vehicle Restart Required: No
* Min/Max values (0, 300)
### 3-4 Bar Change Over
When your speed (in MPH) is below this setting, Auto Follow will set the follow setting to three bars.
When you reach this speed (in MPH), Auto Follow will set the follow setting to four bars.
* Default: 65
* Units: MPH
* Vehicle Restart Required: No
* Min/Max values (0, 300)

## ACC Eco
ACC Eco limits acceleration by keep the ACC cruise speed closer to your current speed.
These setting are how far ahead, in MPH, of your current speed ACC will be set.  
The higher the number, the more aggressive ACC will be when accelerating.
### Keep ahead at ACC Eco level 1
Use this setting to adjust ACC Eco level 1 (one green leaf) for a balance of speed and eco-ness  
* Default: 7
* Units: MPH
* Vehicle Restart Required: No
* Min/Max values 1, 100
### Keep ahead at ACC Eco level 2
Use this setting to adjust ACC Eco level 2 (two green leaves) for maximum eco-ness
* Default: 5
* Units: MPH
* Vehicle Restart Required: No
* Min/Max values 1, 100

## No steer alert 
When this is enabled, you will hear a chime when your vehicle drops to a certain speed and can no longer be steered.
* Default: On
* Vehicle Restart Required: No

## jvePilot Control Settings
### Device Offset
Compensate for mounting your device off center in the windshield.
If you mounted your device off center, use this setting to compensate.
Use positive values if your device is to the left of center and negative if it's to the right.
* Default: 0
* Units: Meters
* Vehicle Restart Required: No
* Min/Max values -1, 1


# Advanced settings
These settings are for advanced users doing advanced things. 
Use SSH and opEdit to change these settings.

### Minimum Steer Check  
When disabled, jvePilot will no longer put a minimum on steer speed.
Requires a mod like a [hardware interceptor](https://github.com/xps-genesis/panda/tree/xps_wp_chrysler_basic).
* Setting: `steer.checkMinimum`
* Default: True 
* Vehicle Restart Required: Yes
* Allowed values: False, True
---

![](https://user-images.githubusercontent.com/37757984/127420744-89ca219c-8f8e-46d3-bccf-c1cb53b81bb1.png)

Table of Contents
=======================

* [What is openpilot?](#what-is-openpilot)
* [Running in a car](#running-in-a-car)
* [Running on PC](#running-on-pc)
* [Community and Contributing](#community-and-contributing)
* [User Data and comma Account](#user-data-and-comma-account)
* [Safety and Testing](#safety-and-testing)
* [Directory Structure](#directory-structure)
* [Licensing](#licensing)

---

What is openpilot?
------

[openpilot](http://github.com/commaai/openpilot) is an open source driver assistance system. Currently, openpilot performs the functions of Adaptive Cruise Control (ACC), Automated Lane Centering (ALC), Forward Collision Warning (FCW) and Lane Departure Warning (LDW) for a growing variety of [supported car makes, models and model years](docs/CARS.md). In addition, while openpilot is engaged, a camera based Driver Monitoring (DM) feature alerts distracted and asleep drivers. See more about [the vehicle integration and limitations here](docs/INTEGRATION.md).

<table>
  <tr>
    <td><a href="https://www.youtube.com/watch?v=mgAbfr42oI8" title="YouTube" rel="noopener"><img src="https://i.imgur.com/kAtT6Ei.png"></a></td>
    <td><a href="https://www.youtube.com/watch?v=394rJKeh76k" title="YouTube" rel="noopener"><img src="https://i.imgur.com/lTt8cS2.png"></a></td>
    <td><a href="https://www.youtube.com/watch?v=1iNOc3cq8cs" title="YouTube" rel="noopener"><img src="https://i.imgur.com/ANnuSpe.png"></a></td>
    <td><a href="https://www.youtube.com/watch?v=Vr6NgrB-zHw" title="YouTube" rel="noopener"><img src="https://i.imgur.com/Qypanuq.png"></a></td>
  </tr>
  <tr>
    <td><a href="https://www.youtube.com/watch?v=Ug41KIKF0oo" title="YouTube" rel="noopener"><img src="https://i.imgur.com/3caZ7xM.png"></a></td>
    <td><a href="https://www.youtube.com/watch?v=NVR_CdG1FRg" title="YouTube" rel="noopener"><img src="https://i.imgur.com/bAZOwql.png"></a></td>
    <td><a href="https://www.youtube.com/watch?v=tkEvIdzdfUE" title="YouTube" rel="noopener"><img src="https://i.imgur.com/EFINEzG.png"></a></td>
    <td><a href="https://www.youtube.com/watch?v=_P-N1ewNne4" title="YouTube" rel="noopener"><img src="https://i.imgur.com/gAyAq22.png"></a></td>
  </tr>
</table>


Running in a car
------

To use openpilot in a car, you need four things
* This software. It's free and available right here.
* One of [the 140+ supported cars](docs/CARS.md). We support Honda, Toyota, Hyundai, Nissan, Kia, Chrysler, Lexus, Acura, Audi, VW, and more. If your car is not supported, but has adaptive cruise control and lane keeping assist, it's likely able to run openpilot.
* A supported device to run this software. This can be a [comma two](https://comma.ai/shop/products/two), [comma three](https://comma.ai/shop/products/three), or if you like to experiment, a [Ubuntu computer with webcams](https://github.com/commaai/openpilot/tree/master/tools/webcam).
* A way to connect to your car. With a comma two or three, you need only a [car harness](https://comma.ai/shop/products/car-harness). With an EON Gold or PC, you also need a [black panda](https://comma.ai/shop/products/panda).

We have detailed instructions for [how to install the device in a car](https://comma.ai/setup).

Running on PC
------

All of openpilot's services can run as normal on a PC, even without special hardware or a car. To develop or experiment with openpilot you can run openpilot on recorded or simulated data.

With openpilot's tools you can plot logs, replay drives and watch the full-res camera streams. See [the tools README](tools/README.md) for more information.

You can also run openpilot in simulation [with the CARLA simulator](tools/sim/README.md). This allows openpilot to drive around a virtual car on your Ubuntu machine. The whole setup should only take a few minutes, but does require a decent GPU.


Community and Contributing
------

openpilot is developed by [comma](https://comma.ai/) and by users like you. We welcome both pull requests and issues on [GitHub](http://github.com/commaai/openpilot). Bug fixes and new car ports are encouraged. Check out [the contributing docs](docs/CONTRIBUTING.md).

You can add support for your car by following guides we have written for [Brand](https://blog.comma.ai/how-to-write-a-car-port-for-openpilot/) and [Model](https://blog.comma.ai/openpilot-port-guide-for-toyota-models/) ports. Generally, a car with adaptive cruise control and lane keep assist is a good candidate. [Join our Discord](https://discord.comma.ai) to discuss car ports: most car makes have a dedicated channel.

Want to get paid to work on openpilot? [comma is hiring](https://comma.ai/jobs/).

And [follow us on Twitter](https://twitter.com/comma_ai).

User Data and comma Account
------

By default, openpilot uploads the driving data to our servers. You can also access your data through [comma connect](https://connect.comma.ai/). We use your data to train better models and improve openpilot for everyone.

openpilot is open source software: the user is free to disable data collection if they wish to do so.

openpilot logs the road facing cameras, CAN, GPS, IMU, magnetometer, thermal sensors, crashes, and operating system logs.
The driver facing camera is only logged if you explicitly opt-in in settings. The microphone is not recorded.

By using openpilot, you agree to [our Privacy Policy](https://comma.ai/privacy). You understand that use of this software or its related services will generate certain types of user data, which may be logged and stored at the sole discretion of comma. By accepting this agreement, you grant an irrevocable, perpetual, worldwide right to comma for the use of this data.

Safety and Testing
----

* openpilot observes ISO26262 guidelines, see [SAFETY.md](docs/SAFETY.md) for more details.
* openpilot has software in the loop [tests](.github/workflows/selfdrive_tests.yaml) that run on every commit.
* The code enforcing the safety model lives in panda and is written in C, see [code rigor](https://github.com/commaai/panda#code-rigor) for more details.
* panda has software in the loop [safety tests](https://github.com/commaai/panda/tree/master/tests/safety).
* Internally, we have a hardware in the loop Jenkins test suite that builds and unit tests the various processes.
* panda has additional hardware in the loop [tests](https://github.com/commaai/panda/blob/master/Jenkinsfile).
* We run the latest openpilot in a testing closet containing 10 comma devices continuously replaying routes.

Directory Structure
------
    .
    ├── cereal              # The messaging spec and libs used for all logs
    ├── common              # Library like functionality we've developed here
    ├── docs                # Documentation
    ├── opendbc             # Files showing how to interpret data from cars
    ├── panda               # Code used to communicate on CAN
    ├── third_party         # External libraries
    ├── pyextra             # Extra python packages
    └── selfdrive           # Code needed to drive the car
        ├── assets          # Fonts, images, and sounds for UI
        ├── athena          # Allows communication with the app
        ├── boardd          # Daemon to talk to the board
        ├── camerad         # Driver to capture images from the camera sensors
        ├── car             # Car specific code to read states and control actuators
        ├── common          # Shared C/C++ code for the daemons
        ├── controls        # Planning and controls
        ├── debug           # Tools to help you debug and do car ports
        ├── locationd       # Precise localization and vehicle parameter estimation
        ├── logcatd         # Android logcat as a service
        ├── loggerd         # Logger and uploader of car data
        ├── modeld          # Driving and monitoring model runners
        ├── proclogd        # Logs information from proc
        ├── sensord         # IMU interface code
        ├── test            # Unit tests, system tests, and a car simulator
        └── ui              # The UI

Licensing
------

openpilot is released under the MIT license. Some parts of the software are released under other licenses as specified.

Any user of this software shall indemnify and hold harmless Comma.ai, Inc. and its directors, officers, employees, agents, stockholders, affiliates, subcontractors and customers from and against all allegations, claims, actions, suits, demands, damages, liabilities, obligations, losses, settlements, judgments, costs and expenses (including without limitation attorneys’ fees and costs) which arise out of, relate to or result from any use of this software by user.

**THIS IS ALPHA QUALITY SOFTWARE FOR RESEARCH PURPOSES ONLY. THIS IS NOT A PRODUCT.
YOU ARE RESPONSIBLE FOR COMPLYING WITH LOCAL LAWS AND REGULATIONS.
NO WARRANTY EXPRESSED OR IMPLIED.**

---

<img src="https://d1qb2nb5cznatu.cloudfront.net/startups/i/1061157-bc7e9bf3b246ece7322e6ffe653f6af8-medium_jpg.jpg?buster=1458363130" width="75"></img> <img src="https://cdn-images-1.medium.com/max/1600/1*C87EjxGeMPrkTuVRVWVg4w.png" width="225"></img>

[![openpilot tests](https://github.com/commaai/openpilot/workflows/openpilot%20tests/badge.svg?event=push)](https://github.com/commaai/openpilot/actions)
[![Total alerts](https://img.shields.io/lgtm/alerts/g/commaai/openpilot.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/commaai/openpilot/alerts/)
[![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/commaai/openpilot.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/commaai/openpilot/context:python)
[![Language grade: C/C++](https://img.shields.io/lgtm/grade/cpp/g/commaai/openpilot.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/commaai/openpilot/context:cpp)
[![codecov](https://codecov.io/gh/commaai/openpilot/branch/master/graph/badge.svg)](https://codecov.io/gh/commaai/openpilot)
