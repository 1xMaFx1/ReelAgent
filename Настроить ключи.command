#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 scripts/launch.py --setup
printf '\nНажмите Enter, чтобы закрыть окно.'
read -r
