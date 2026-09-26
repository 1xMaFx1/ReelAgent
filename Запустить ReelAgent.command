#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 scripts/launch.py
result=$?
if [ "$result" -ne 0 ]; then
  printf '\nНажмите Enter, чтобы закрыть окно.'
  read -r
fi
exit "$result"
