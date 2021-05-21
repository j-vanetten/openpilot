echo $$ > /dev/cpuset/app/tasks
# (our parent, tmux, also gets all the cores)
echo $PPID > /dev/cpuset/app/tasks

