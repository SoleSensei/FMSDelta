# ----------------------------------------------------------------- #
# Скрипт скачивает реестр недействительных паспортов с ФМС МВД и    #
# вычисляет новые добавленные и удаленные паспорта                  #
# ----------------------------------------------------------------- #
# GlowByte                                                          #
# Автор: Гончаренко Дмитрий                                         #
# Версия: v2.1                                                      #
# ----------------------------------------------------------------- #

import sys, time, bz2, os, argparse
import requests  # pip3 install requests
import multiprocessing as mp
from datetime import datetime
from functools import partial
from math import ceil

# ------------------------------ Динамические переменные ------------------------------ #

# Ссылка на реестр недействительных паспортов с сайта МВД
fms_url = 'http://guvm.mvd.ru/upload/expired-passports/list_of_expired_passports.csv.bz2'
# Флаг запуска. Поставить 1 при первичном запуске. Скачивание + парсинг. Без дельты.
pure_start = 0
# Флаг завершения. По умолчанию очищает директорию от временных файлов и старых бэкапов.
clean_finish = 1
# Требуется ли загрузка в Кронос Синопсис
cronos = 1
# Формат файлов
fformat = '.txt'
# Вид бэкап файлов. Сейчас: list_of_expired_passports_date.txt, delta_date.txt
postfix = datetime.today().strftime('%Y%m%d')  # _date.fformat
# Выбор функции вычисления дельты. Стабильная - медленная, включать при больших дельта
delta_method = 'flow'  # 'onepass' / 'stable' / 'flow'
delta_type = 'plus'  # 'plus' / 'minus' / 'all'
# Количество используемой оперативной памяти. Связано с размером блока паспортов.
ram_use = '2GB'  # [MB|GB] exm: '2GB 700MB'
# ОКАТО коды регионов
# okato_codes = [1, 3, 4, 5, 7, 8, 11, 12, 14, 15, 17, 19, 20, 22, 24, 25, 26, 27, 28, 29, 32, 33, 34, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99]

# ------------------------------------------------------------------------------------- #


# Проверяет состоит ли строка только из цифр
def isInteger(s):
    try:
        int(s)
        return True
    except ValueError:
        return False


# Размер блока чтения (в строках). Больше значение - Больше расход RAM
blocksize = 20 * 10 ** 6  # 1200MB
# Переводит RAM в размер блока в строках
def toBlock(ram):
    global blocksize
    mblock = 600  # 5m ~ 600MB
    isGB = ram.find('GB')
    isMB = ram.find('MB')
    if isGB == isMB:
        print('Error in ram_use variable:', ram_use, 'Using default RAM')
        print('Example: \'1GB 200MB\'')
        logging('Using default RAM')
        ram = '1GB'
        isGB = 1
    print('RAM USING:', ram)
    logging('RAM USING: ' + ram)
    sizeGB = 0
    sizeMB = 0
    if isGB != -1:
        partGB, ram = ram.split('GB')
        sizeGB = int(partGB)
    if isMB != -1:
        partMB, ram = ram.split('MB')
        sizeMB = int(partMB)
    size = sizeGB * 2**10 + sizeMB
    blocksize = int(size / mblock * (5 * 10 ** 6))
    print('Blocksize computed: ' + str(blocksize // 10**6) + 'm passports!')
    logging('Blocksize computed: ' + str(blocksize // 10**6) + 'm passports!')


# Конвертирует файл с номерами паспортов в формат для загрузки в Кронос
def formatCronos(file, name):
    print('Converting File to Cronos format')
    logging('Converting File to Cronos format')
    start_package = '++ ДД'  # начало пакета
    end_package = '++ ЯЯ'  # конец пакета
    start_message = '++ НН'  # начало сообщения
    end_message = '++ КК'  # конец сообщения
    div = '‡'  # разделитель
    mnemo_code = '++ МП'  # мнемокод базы
    # Начало строки
    start_ = start_package + div + start_message + div + mnemo_code + div
    # Конец строки
    _end = div + end_message + div + end_package + div
    with open(file, 'r') as fd, open(name + postfix, 'w') as cron:
            print(file + ' converting to ' + name + postfix)
            logging(file + ' converting to ' + name + postfix)
            file_len = sum(1 for n in fd)
            fd.seek(0)
            for k, line in enumerate(fd):
                cron.write(start_ + '01 ' + line[:4] + div + '02 ' + line[4:10] + _end)
                if k < file_len - 1:
                    cron.write('\n')
                if k % 1000 == 0:
                    print(str(k * 100 // file_len) + '%', end='\r')
    print('Converted!')
    logging('Converted!')


# Запись в лог
def logging(text, noTime=0):
    with open('./log/log' + postfix, 'a') as log:
        if noTime:
            print(text, file=log)
        else:
            print(datetime.today().strftime('[%Y-%m-%d %H:%M:%S] ') + text, file=log)


# Скачивание файла по ссылке
def downloadFile(url):
    filename = url.split('/')[-1]
    print('Downloading:', filename)
    logging('Downloading: ' + filename)
    # Если файл уже существует - пропуск
    if os.path.exists(filename):
        print(filename, 'exists! Skipped!')
        logging(filename + ' exists! Skipped!')
        return filename

    r = requests.get(url, stream=True)
    with open(filename, 'wb') as f:
        size = 0
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                if size % 10240 == 0:
                    print('Downloaded:', str(size // 1024) + 'MB', end='\r')
                f.write(chunk)
                f.flush()
                size += 1
    print('Downloaded:', filename, str(size // 1024) + 'MB')
    logging('Downloaded: ' + filename + ' ' + str(size // 1024) + 'MB')
    return filename


# Разархивирование bz2
def decompressFile(filename='list_of_expired_passports.csv.bz2'):
    print('Extracting:', filename)
    logging('Extracting: ' + filename)
    # Если файл уже существует - пропуск
    if os.path.exists(filename[:-len(fformat)]):
        print(filename[:-len(fformat)], 'exists! Skipped!')
        logging(filename[:-len(fformat)] + ' exists! Skipped!')
        return filename[:-len(fformat)]

    with open(filename[:-len(fformat)], 'wb') as csvfile, open(filename, 'rb') as zipfile:
        z = bz2.BZ2Decompressor()
        for block in iter(lambda: zipfile.read(512 * 1024), b''):
            csvfile.write(z.decompress(block))
    print('Extracted', filename[:-len(fformat)])
    logging('Extracted ' + filename[:-len(fformat)])
    return filename[:-len(fformat)]


# Удаление всех данных кроме вида: 1234,123456 (считаются ошибочными)
def parseCSV(filename='list_of_expired_passports.csv'):
    print('Parsing:', filename)
    logging('Parsing ' + filename)
    pfilename = filename[:-len(fformat)] + postfix
    num = 0
    err = 0
    # Если файл уже существует - пропуск
    if os.path.exists(pfilename):
        with open(pfilename, 'r') as pfile:
            num = sum(1 for i in pfile)
        print(pfilename, 'exists!', num, 'passports! Skipped!')
        logging(pfilename + ' exists! ' + str(num) + ' passports! Skipped!')
        return num, pfilename

    with open(filename, 'r', encoding='utf8') as csvIN, \
            open(pfilename, 'w') as txtOUT, \
            open('brokenData.txt', 'w') as txtBroke:
        next(csvIN)
        for line in csvIN:
            a, b = line.replace('\n', '').split(',')
            if len(a) == 4 and len(b) == 6 and (a+b).isdigit():
                txtOUT.write(a + b + '\n')
                num += 1
                if num % 10**5 == 0:
                    print('Passports:', num, end='\r')
            else:
                err += 1
                txtBroke.write(a + ',' + b + '\n')
        print('Parsed', num, 'passports!')
        print('File:', pfilename)
        print('Broken Data: brokenData.txt (' + str(err) + ')')
        logging('Parsed ' + str(num) + ' passports!\nFile: ' +
                pfilename + '\nBroken Data: brokenData.txt (' + str(err) + ')')
        return num, pfilename


# Поиск в директории ./backup самого последнего файла по postfix дате
def getBackFile(filename='list_of_expired_passports.csv'):
    print('Getting backup file to compare')
    logging('Getting backup file to compare')
    n = len(postfix) - 1
    flen = len(fformat)
    f = []
    for _, _, files in os.walk('./backup'):
        f.extend(files)
        break
    if len(f) == 0:
        print('No backup files! Set \'pure_start = 1\' Abort.')
        logging('No backup files! Set \'pure_start = 1\' Abort.')
        exit()
    last = 0  # последний бэкап
    first = 0  # первый бэкап
    for file in f:
        end_f = file[-n:-flen]
        if not isInteger(end_f):
            print('Postfix error: not a number! Abort.', end_f)
            logging('Postfix error: not a number! Abort. ' + end_f)
            exit()
        if last < int(end_f):
            last = int(end_f)
            first = last if first == 0 else first
        if first > int(end_f):
            first = int(end_f)
    print('Got first backup:', first)
    print('Got last backup:', last)
    logging('Got first backup: ' + str(first) +
            ' Got last backup: ' + str(last))
    return (filename[:-flen] + '_' + str(first) + fformat), (filename[:-flen] + '_' + str(last) + fformat)


# Переводит строку в необходимый формат для записи в стек
def setFormat(line):
    if line[0] == '0':
        return line.replace('\n', '')
    return int(line)


# Вычисление дельты (только инкремент) ~ 6 мин
# fileOld - предыдущая версия
# fileNew - новая версия
# N - количество людей в новой базе
def caclDeltaFlow(fileOld, fileNew, N):
    print('Delta Flow started!')
    logging('Delta Flow started!')
    print('Comparing:', fileOld, fileNew)
    logging('Comparing: ' + fileOld + ' ' + fileNew)
    stackN = set()
    tmp_ = set()
    isEnded = False
    with open('deltaPlus' + postfix, 'w') as deltaPlus:
        k = 0
        n = 0
        with open(fileNew, 'r') as txtNEW:
            for lineN in txtNEW:
                n += 1
                stackN.add(setFormat(lineN))
                if len(stackN) > blocksize:
                    k += 1
                    print('Next block:', k, 'Passports:', n)
                    with open('./backup/' + fileOld, 'r') as txtOLD:
                        for lineO in txtOLD:
                            elemO = setFormat(lineO)
                            if elemO in stackN:
                                stackN.remove(elemO)
                                lineN = txtNEW.readline()
                                n += 1
                                if not lineN:
                                    isEnded = True
                                    break
                                tmp_.add(setFormat(lineN))
                            elif elemO in tmp_:
                                tmp_.remove(elemO)
                                lineN = txtNEW.readline()
                                n += 1
                                if not lineN:
                                    isEnded = True
                                    break
                                tmp_.add(setFormat(lineN))
                    if not isEnded:
                        for elemO in stackN:
                            print(elemO, end='\n', file=deltaPlus)
                        stackN.clear()
                        stackN.update(tmp_)
                        tmp_.clear()
            stackN.update(tmp_)
            tmp_.clear()
            with open('./backup/' + fileOld, 'r') as txtOLD:
                for lineO in txtOLD:
                    elemO = setFormat(lineO)
                    if elemO in stackN:
                        stackN.remove(elemO)
        for elemO in stackN:
            print(elemO, end='\n', file=deltaPlus)
        stackN.clear()
    print('Compared!')
    logging('Compared!')


# Вычисление дельты (быстрая версия, 1 прогон) ~ 5 мин
# fileOld - предыдущая версия
# fileNew - новая версия
# N - количество людей в новой базе
def calcDeltaOnePass(fileOld, fileNew, N):

    # Если дельта > 1гб сравнить до конца файла.
    def calcSkip(file, stack, N, start_from, t):
        print('Delta ' + t + ' is too big, comparing to the end of file')
        logging('Delta ' + t + ' is too big, comparing to the end of file')
        n = 0
        with open(file, 'r') as txt:
            for line in txt:
                n += 1
                elem = setFormat(line)
                if elem in stack:
                    stack.remove(elem)
                    if len(stack) == 0:
                        break
                if n % 10**5 == 0:
                    print(N - n, end='\r')
        print('Cleared to the end: delta', t)
        logging('Cleared to the end: delta ' + t)
        return stack

    print('Delta One Pass started!')
    logging('Delta One Pass started!')
    print('Comparing:', fileOld, fileNew)
    logging('Comparing: ' + fileOld + ' ' + fileNew)
    with open('./backup/' + fileOld, 'r') as fold:
        print('Counting passports in', fileOld)
        O = sum(1 for i in fold)
    print('Counted! (' + str(O) + ')')
    logging('Counted passports in ' + fileOld + ' (' + str(O) + ')')
    less_num = N if N < O else O
    # Вычисление
    print('Calculating delta')
    stackMinus = set()
    stackPlus = set()
    skip_flg = False
    # for code in okato_codes:
    with open('deltaPlus' + postfix, 'w') as deltaPlus, open('deltaMinus' + postfix, 'w') as deltaMinus:
        k = 0
        with open(fileNew, 'r') as txtNEW, open('./backup/' + fileOld, 'r') as txtOLD:
            for lineO, lineN in zip(txtOLD, txtNEW):
                elemO = setFormat(lineO)
                elemN = setFormat(lineN)
                k += 1
                if k % 100000 == 0:
                    print(less_num - k, end='\r')
                if elemO != elemN:
                    stackMinus.add(elemO)
                    stackPlus.add(elemN)
                if k % (2 * 10 ** 6) == 0:
                    ins_ = stackMinus.intersection(stackPlus)
                    stackMinus.difference_update(ins_)
                    stackPlus.difference_update(ins_)
                    ins_.clear()
                    # Защита от переполнения RAM
                    if len(stackPlus) + len(stackMinus) > 2*blocksize:
                        skip_flg = True
                        if len(stackPlus) > len(stackMinus):
                            stackPlus = calcSkip('./backup/' + fileOld, stackPlus, O,  k, 'plus')
                            for element in stackPlus:
                                print(element, end='\n', file=deltaPlus)
                            stackPlus.clear()
                        else:
                            stackMinus = calcSkip(fileNew, stackMinus, N, k, 'minus')
                            for element in stackMinus:
                                print(element, end='\n', file=deltaMinus)
                            stackMinus.clear()

            for i in range(0, abs(N - O)):
                if N > O:
                    elemN = setFormat(txtNEW.readline())
                    stackPlus.add(elemN)
                else:
                    elemO = setFormat(txtOLD.readline())
                    stackMinus.add(elemO)
                if i % (10 ** 6) == 0:
                    ins_ = stackMinus.intersection(stackPlus)
                    stackMinus.difference_update(ins_)
                    stackPlus.difference_update(ins_)
                    ins_.clear()
                    # Защита от переполнения RAM
                    if len(stackPlus) + len(stackMinus) > 2*blocksize:
                        skip_flg = True
                        if len(stackPlus) > len(stackMinus):
                            stackPlus = calcSkip('./backup/' + fileOld, stackPlus, O,  k, 'plus')
                            for element in stackPlus:
                                print(element, end='\n', file=deltaPlus)
                            stackPlus.clear()
                        else:
                            stackMinus = calcSkip(fileNew, stackMinus, N, k, 'minus')
                            for element in stackMinus:
                                print(element, end='\n', file=deltaMinus)
                            stackMinus.clear()

            ins_ = stackMinus.intersection(stackPlus)
            stackMinus.difference_update(ins_)
            stackPlus.difference_update(ins_)
            ins_.clear()
            if skip_flg:
                stackPlus = calcSkip('./backup/' + fileOld, stackPlus, O,  k, 'plus')
                stackMinus = calcSkip(fileNew, stackMinus, N, k, 'minus')

            print('Calculated! Writing delta to files.')
            logging('Calculated! Writing delta to files.')
            for element in stackPlus:
                print(element, end='\n', file=deltaPlus)
            for element in stackMinus:
                print(element, end='\n', file=deltaMinus)
            stackPlus.clear()
            stackMinus.clear()
    print('Compared!')
    logging('Compared!')


# --------------------------------------- Параллельная обработка --------------------------------------- #


# Функция прослушивающая очередь и записывающая дельту в файл
def writer(stackQueue, file):
    print('Writer: starts!')
    with open(file, 'w') as f:
        while 1:
            stack = stackQueue.get()
            print('Writer: got message!')
            if stack == 'exit':
                break
            print('Writer: write stack!')
            for elem in stack:
                print(elem, end='\n', file=f)
            stack.clear()
    print('Writer: finished!')
    return


# Функция многопропоточного сравнения блоков для calcDeltaStable, отправляет данные в очередь
def delta_parallel(np, delta, file1, file2, stackQueue, N, blocksize, procs=1):
    block = round((N if N <= blocksize else blocksize) / procs)  # число строк в одном блоке
    blocks = ceil(N / block)  # число блоков в файле
    p_blocks = round(blocks / procs)  # число блоков в обработке у каждого процесса
    p_start = p_blocks * block * np  # начало параллельного блока (строка)
    print('Proc:', np + 1, 'Start from:', p_start)
    stackO = set()
    stackN = set()
    k = 0
    with open(file1, 'r') as fileN:
        for i in range(0, p_start):
            next(fileN)
        for i in range(0, p_blocks):
            print('Proc:', np + 1, 'Block:', i + 1, '/', p_blocks)
            for k, line in enumerate(fileN):
                stackN.add(setFormat(line))
                if k == block - 1: break
            with open(file2, 'r') as fileO:
                for k, line in enumerate(fileO):
                    stackO.add(setFormat(line))
                    if k % block == 0 and k > 0:
                        stackN.difference_update(stackO)
                        stackO.clear()
                        if len(stackN) == 0: break
                if len(stackN) > 0 and len(stackO) > 0:
                    stackN.difference_update(stackO)  # проверяем оставшиеся записи
            stackO.clear()
            print('Proc:', np + 1, 'Sending delta to writer!')
            stackQueue.put(stackN.copy())
            stackN.clear()
        # Оставшиеся строки обрабатывает последний процесс
        if np == procs:
            print('Proc:', np + 1, 'Last pass processing!')
            for line in fileN:
                stackO.add(setFormat(line))
            with open(file2, 'r') as fileO:
                for line in fileO:
                    elem = setFormat(line)
                    if elem in stackO:
                        stackO.remove(elem)
            print('Proc:', np + 1, 'Sending delta to writer!')
            stackQueue.put(stackO.copy())
            stackO.clear()
    print('Proc ended!:', np + 1)
    return

# ------------------------------------------------------------------------------------------------------ #

# Вычисление дельты (дельта > 1гб) ~ 40 мин
# fileOld - предыдущая версия
# fileNew - новая версия
# N - количество людей в новой базе
def calcDeltaStable(fileOld, fileNew, N):

    # Подготовка к параллельной обработке
    def compare_parallel(delta, file1, file2, procs=3):
        print('Parallel processing starts! Processes=', procs)
        logging('Parallel processing starts! Processes=' + str(procs))
        print('Main: Pool creating!')
        logging('Main: Pool creating!')
        # Настройка
        pool = mp.Pool(processes=procs + 1)  # 1 - writer. остальные - обработка
        manager = mp.Manager()
        queue = manager.Queue()
        # Подготовка аргументов для загрузки в delta_parallel
        compare_args = partial(delta_parallel, delta=delta, file1=file1, file2=file2, stackQueue=queue, N=N, blocksize=blocksize, procs=procs)
        # Создание процессов и обработка
        w = pool.apply_async(writer, args=(queue, delta))  # процесс writer
        print('Main: Wait for processes finished!')
        pool.map(compare_args, range(0, procs))  # procs процесса сравнения
        print('Main: sending \'exit\' to writer!')
        queue.put('exit')
        w.get()  # ожидание завершения writer
        pool.close()
        print('Pool closed!')

    print('Delta Stable started!')
    logging('Delta Stable started!')
    print('Comparing:', fileOld, fileNew)
    logging('Comparing: ' + fileOld + ' ' + fileNew)
    # Вычисление дельты с delta_type
    if delta_type == 'plus' or delta_type == 'all':
        compare_parallel('deltaPlus' + postfix, fileNew, './backup/' + fileOld)
    if delta_type == 'minus' or delta_type == 'all':
        compare_parallel('deltaMinus' + postfix, './backup/' + fileOld, fileNew)
    print('Compared!')
    logging('Compared!')


# Выбирает метод вычисления дельты
def calcDelta(backup_file, parsed_file, num_passports):
    if delta_method == 'onepass':
        calcDeltaOnePass(backup_file, parsed_file, num_passports)
    elif delta_method == 'stable':
        calcDeltaStable(backup_file, parsed_file, num_passports)
    elif delta_method == 'flow':
        caclDeltaFlow(backup_file, parsed_file, num_passports)


# Парсер параметров командной строки
def usage():
    parser = argparse.ArgumentParser(description='FMS Parser and Delta Calculator')
    parser.add_argument('--pure', help='Set for first run, just parsing, no delta', action='store_true')
    parser.add_argument('--noclean', help='Set to leave directory unclean from temorary files', action='store_true')
    parser.add_argument('-m', metavar='method', help='Delta calculation method: [stable|onepass|flow]. Default: \'flow\'')
    parser.add_argument('-t', metavar='type', help='Delta calcultation type: [plus|minus|all]. Default: \'plus\'')
    parser.add_argument('-r', metavar='ram', help='Set RAM limit for the program. exp: \'2GB500MB\'')
    return parser.parse_args()


# Функция инициализации.
def init():
    global postfix, ram_use, delta_method, pure_start, clean_finish, delta_type, args; args = usage()
    # Редактирование глобальных переменных в зависимости от аргументов выставленных пользователем
    postfix = '_' + postfix + fformat
    if args.pure: pure_start = 1
    if args.noclean: clean_finish = 0
    if args.m: delta_method = args.m
    if args.t: delta_type = args.t
    if args.r: ram_use = args.r
    # При первичном запуске создать папку backup, delta, log
    if not os.path.isdir('./backup'):
        os.mkdir('./backup')
    if not os.path.isdir('./delta'):
        os.mkdir('./delta')
    if not os.path.isdir('./cronos'):
        os.mkdir('./cronos')
    if not os.path.isdir('./log'):
        os.mkdir('./log')
    if not os.path.exists('./log/log' + postfix):
        open('./log/log' + postfix, 'a').close()

    # Начальное логирование
    logging('# ----------------------------------------------------------------------------------------- #', 1)
    logging('New log starts: ' + datetime.today().strftime('%d/%m/%y %H:%M'), 1)
    logging('------------ Variables ------------', 1)
    logging('Start type: ' + ('pure' if pure_start else 'not pure'), 1)
    logging('Delta calculation method: ' + delta_method, 1)
    logging('Delta calculation type: ' + delta_type, 1)
    logging('Postfix style: ' + postfix, 1)
    logging('Clean finish: ' + ('yes' if clean_finish else 'no'), 1)
    logging('-----------------------------------', 1)
    if delta_method not in ('stable', 'onepass', 'flow'):
        print('delta_method error: \'stable\' or \'onepass\' or \'flow\' expected! Abort.')
        logging('delta_method error: \'stable\' or \'onepass\' or \'flow\' expected! Abort.')
        exit()
    if delta_type not in ('plus', 'minus', 'all'):
        print('delta_type error: \'plus\' or \'minus\' or \'all\' expected! Abort.')
        logging('delta_type error: \'plus\' or \'minus\' or \'all\' expected! Abort.')
        exit()
    if delta_method == 'flow' and delta_type != 'plus':
        print('Error: Flow calculation method has no \'' + delta_type + '\' delta!')
        logging('Error: Flow calculation method has no \'' + delta_type + '\' delta!')
        exit()
    if delta_method == 'onepass' and delta_type != 'all':
        print('Warning: One Pass calculation method can\'t compute just \'' + delta_type + '\' delta! Switching type on \'all\'')
        logging('Warning: One Pass calculation method can\'t compute just \'' + delta_type + '\' delta! Switching type on \'all\'')
        delta_type = 'all'
    print('Delta method:', delta_method)
    print('Delta type:', delta_type)
    # Перевод переменной оперативной памяти в размер блока чтения в строках
    toBlock(ram_use)


# Функция завершения. Перенос файлов и очистка директории
def postprocessing(parsed_file, first_backup, file='list_of_expired_passports.csv', compressfile='list_of_expired_passports.csv.bz2'):
    print('Postprocessing')
    logging('Postprocessing', 1)

    # Перенесет файлы, если они существуют, с заменой
    def softmove(loc, dist):
        if os.path.exists(dist + loc) and os.path.exists(loc):
            os.remove(dist + loc)
        if os.path.exists(loc):
            os.rename(loc, dist + loc)

    # Переносим файлы в бэкап и дельту с заменой
    softmove(parsed_file, './backup/')
    softmove('deltaPlus' + postfix, './delta/')
    softmove('deltaMinus' + postfix, './delta/')
    softmove('cronos_add' + postfix, './cronos/')
    softmove('cronos_del' + postfix, './cronos/')

    if clean_finish:
        # Удаляем самый старый бэкап, если > 3
        f = []
        for _, _, files in os.walk('./backup'):
            f.extend(files)
            break
        if len(f) > 3 and os.path.exists('./backup/' + first_backup):
            os.remove('./backup/' + first_backup)
            print('./backup/' + first_backup + ' removed')
            logging('./backup/' + first_backup + ' removed', 1)

        # Очистка work directory
        os.remove(compressfile)
        os.remove(file)
        print(compressfile + ' and ' + file + ' removed')
        logging(compressfile + ' and ' + file + ' removed', 1)
    logging('# ----------------------------------------------------------------------------------------- #', 1)


# Тело основной программы
def main():
    print('Starts passports parser!')
    t0 = time.time()

    # Инициализация
    init()

    # Скачиваем реестр недействительных паспортов
    compressfile = downloadFile(fms_url)
    # Распаковываем архив в текущую директорию
    first_backup = file = decompressFile(compressfile)
    # Подчищаем файл от битых данных
    num_passports, parsed_file = parseCSV(file)
    # Если запуск первый, то сохранить только бэкап
    if not pure_start:
        # Получение имени предыдущей версии реестра для вычисления дельты
        first_backup, backup_file = getBackFile(file)
        # Сравнение старой и новой версии баз, выделение дельты
        calcDelta(backup_file, parsed_file, num_passports)
        # Конвертирование в формат Кроноса
        if cronos:
            # Если файлы существуют
            if delta_type == 'plus' or delta_type == 'all':
                formatCronos('deltaPlus' + postfix, 'cronos_add')
            if delta_type == 'minus' or delta_type == 'all':
                formatCronos('deltaMinus' + postfix, 'cronos_del')

    t1 = time.time()
    print('Parser ended!')
    print('Time: ', '{:g}'.format((t1 - t0) // 60), 'm ', '{:.0f}'.format((t1 - t0) % 60), 's', sep='')
    logging('---------------\nCompleted!', 1)
    logging('Time: ' + str('{:g}'.format((t1 - t0) // 60)) + 'm ' + str('{:.0f}'.format((t1 - t0) % 60)) + 's', 1)

    # Постобработка - завершение
    postprocessing(parsed_file, first_backup, file, compressfile)


if __name__ == '__main__':
    mp.freeze_support()  # фикс ошибки с pyinstaller и multiprocessing и argparser
    main()
