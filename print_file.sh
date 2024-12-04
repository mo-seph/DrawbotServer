#!/bin/bash

 FILE=$1
 NAME=`basename $FILE`
 scp $FILE drawbot:/tmp/drawbot/$NAME
 ssh drawbot "cd ~/cursivedata/client/; ./feed.py --file /tmp/drawbot/$NAME"
