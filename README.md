# FMS Delta
Скрипт скачивает реестр недействительных паспортов с ФМС МВД и вычисляет новые добавленные и удаленные паспорта

## Краткая информация
Задача выполнена в рамках проекта __GlowByte__

### Ресурсы и инструменты
Использовался __Python 3.7__

#### Система разработки:
- __OS:__ Windows 10 x64
- __RAM:__ 8GB
- __Core:__ i3

#### Ресурсы:
- __115 000 000__ паспортов в реестре
- __900__ MB RAM
- __time__ ~ 20 minutes (all - fast) / 1h (all - stable)
- __time__ ~ 3 minutes (fast calc delta)
- __time__ ~ 40 minutes (stable calc delta)

## Предварительная настройка
Возможна динамическая настройка скрипта через изменение параметров, приведенных ниже.

При первичном запуске сменить `pure_start = 1`. 
```py
# ------------------------------ Динамические переменные ------------------------------ # 

# Ссылка на реестр недействительных паспортов с сайта МВД
fms_url = 'http://guvm.mvd.ru/upload/expired-passports/list_of_expired_passports.csv.bz2'
# Флаг запуска. Поставить 1 при первичном запуске. Скачивание + парсинг. Без дельты.
pure_start = 0
# Флаг завершения. По умолчанию очищает директорию от временных файлов.
clean_finish = 0
# Формат файлов
fformat = '.txt'
# Вид бэкап файлов. Сейчас: list_of_expired_passports_date.txt, delta_date.txt
postfix = datetime.today().strftime('%Y%m%d')  # _date.fformat
# Выбор функции вычисления дельты. Стабильная - медленная, включать при больших дельта
delta_type = 'fast'  # 'fast' / 'stable'
# Количество используемой оперативной памяти. Связано с размером блока паспортов.
ram_use = '2GB 500MB' # [MB|GB] exm: '2GB 700MB' 

# ------------------------------------------------------------------------------------- #
```

## Запуск
Для запуска скрипта необходимо выполнить следующую команду. 
```bash
# using executable 
pure_start.exe # first run
delta_fast.exe # fast calcultations, small delta
delta_stable.exe # stable calcultations, big delta
# using python 3.7
python FMSDelta.py
```
### Сбор executable файла
Для сборки __executable__ файла использовалась утилита `pyinstaller`. 
```bash
# using pyinstaller and python3.6
pip install pyinstaller
pyinstaller --onefile FMSDelta.py
```

## Результат
### Структура проекта
```py
-backup/ # директория с файлами бэкапов, не больше трех штук, автоматическое удаление
-delta/ # директория с файлами посчитанных дельт, неограниченное количество
-log/ # директория лог файлов, неограниченное количество
FMSDelta.py # скрипт
pure_start.exe # executable файл скрипта для первичного запуска, с параметром % pure_start = 1 %
delta_fast.exe # executable файл скрипта, с параметром % delta_type = 'fast' %
delta_stable.exe # executable файл скрипта, с параметром % delta_type = 'stable' %
brokenData.txt # текстовый файл, полученный в результате парсинга реестра, содержит битые данные
README.md # этот текстовый документ
```
