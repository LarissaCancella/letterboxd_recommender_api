#!/bin/bash
python main.py &
python worker.py &
wait