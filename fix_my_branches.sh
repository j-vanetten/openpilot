#!/usr/bin/env bash
set -e

set +e
git remote add upstream https://github.com/j-vanetten/openpilot.git

git fetch upstream
git checkout jvePilot-release


set -e
git rebase upstream/jvePilot-release
git push -f origin jvePilot-release

set +e
git branch -D mog
set -e
git checkout -b mog

git merge --squash mog_readme_changes && git commit -m "mog readme changes"
git merge --squash mog_auto_tether && git commit -m "mog auto tether"
git merge --squash mog_steer_below_zero && git commit -m "mog steer below zero"
git merge --squash mog_gui_changes && git commit -m "mog gui changes"
git merge --squash mog_xps_lkas_fix && git commit -m "xps lkas fix"
git merge --squash mog_mqtt && git commit -m "mog mqtt"
