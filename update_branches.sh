#!/usr/bin/env bash

git remote add upstream https://github.com/j-vanetten/openpilot.git

git fetch upstream
git checkout jvePilot-release

set -e

git rebase upstream/jvePilot-release
git push -f origin jvePilot-release

git checkout mog_readme_changes && git rebase origin/jvePilot-release && git push -f
git checkout mog_auto_tether && git rebase origin/jvePilot-release && git push -f
git checkout mog_steer_below_zero && git rebase origin/jvePilot-release && git push -f
git checkout mog_gui_changes && git rebase origin/jvePilot-release && git push -f
git checkout mog_xps_lkas_fix && git rebase origin/jvePilot-release && git push -f
git checkout mog_mqtt && git rebase origin/jvePilot-release && git push -f
