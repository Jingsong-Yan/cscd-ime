#!/usr/bin/env python
# encoding: utf-8
"""
File Description:
Author: rightyonghu
Created Time: 2022/6/28
"""
import argparse
import concurrent.futures
import json
import paddle
import queue
import random
import requests
import threading
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

from util import (PINYIN_DISTANCE_MATRIX, VALID_PINYIN, PinyinInfo, cal_ppl,
                  is_chinese_string, is_nearby_pinyin, seg)


def fetch_google_input_method_result(context, pinyin, target):
    """
    :param context: before context
    :param pinyin: pinyin of input word/char
    :param target: target word/char
    :return:
    """
    params = {
        'text': f"|{context},{pinyin}" if context else pinyin,
        'itc': 'zh-t-i0-pinyin',
        'num': 11,
        'cp': 0,
        'cs': 1,
        'ie': 'utf-8',
        'oe': 'utf-8',
        'app': 'demopage'
    }
    headers = {
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11'
    }
    proxies = {
        "http": "socks5://127.0.0.1:7890",
        "https": "socks5://127.0.0.1:7890"
    }
    url = 'https://inputtools.google.com/request'
    # strs = []
    # for k, v in params.items():
    #     strs.append(f"{k}={v}")
    # url = url + '?' + '&'.join(strs)
    # print(url)
    # data = requests.get(url, headers=headers, proxies=proxies).json()[1][0][1]
    data = requests.post(url, params=params, headers=headers,
                         proxies=proxies).json()[1][0][1]
    # data = []
    if len(data[0]) == len(target) and data[0] != target:
        return data[0]
    cans = [data[i] for i in range(1, 3) if len(
        data[i]) == len(target) and data[i] != target]
    if cans:
        return random.choice(cans)
    return None


def generate_noise():
    """
    generate noise of word_or_char, pinyin_type
    :return:
    """
    if random.random() < 0.45:
        word_or_char = 'char'
    else:
        word_or_char = 'word'
    p = random.random()
    if p < 0.85:
        pinyin_type = 'same'
    else:
        pinyin_type = 'not_same'
    return word_or_char, pinyin_type


def add_noise_to_sentence(text):
    """
    add noise to text
    """
    error_num_p = random.random()
    if error_num_p < 0.6:
        error_num = 1
    else:
        error_num = 2
    initial_fuzzy = [('s', 'sh'), ('c', 'ch'), ('z', 'zh'),
                     ('n', 'l'), ('h', 'f')]  # 声母模糊音
    final_fuzzy = [('en', 'eng'), ('an', 'ang'), ('ian', 'iang'),
                   ('uan', 'uang'), ('in', 'ing')]  # 韵母模糊音
    initial_fuzzy_dict = dict()
    for (a, b) in initial_fuzzy:
        initial_fuzzy_dict[a] = b
        initial_fuzzy_dict[b] = a
    final_fuzzy_dict = dict()
    for (a, b) in final_fuzzy:
        final_fuzzy_dict[a] = b
        final_fuzzy_dict[b] = a
    return_char_list = list(text)
    words = seg(text)
    error_index_set = set()
    pinyin_info = PinyinInfo(text)
    pinyin_info.add_pinyin(add_initial_final=True)
    origin_ppl = cal_ppl(text)
    details = []
    for _ in range(error_num):
        word_or_char, pinyin_type = generate_noise()
        retry_count = 0
        while retry_count < 3:
            retry_count += 1
            if word_or_char == 'char':
                random_index = random.choice(range(len(text)))
                token = text[random_index]
                start, end = random_index, random_index + 1
            else:
                random_word = random.choice(words)
                token, start, end = random_word
                if len(token) == 1:
                    continue
            if not is_chinese_string(token) or any([i in error_index_set for i in range(start, end)]):
                continue
            if pinyin_type == 'same':
                token_pinyin_list = pinyin_info.pinyin_list[start:end]
            else:
                if len(token) > 1:
                    char_index = random.choice(range(len(token)))
                    changed_pinyin_index = char_index + start
                else:
                    changed_pinyin_index = start
                origin_pinyin = pinyin_info.pinyin_list[changed_pinyin_index]
                origin_initial = pinyin_info.initial_list[changed_pinyin_index]
                origin_final = pinyin_info.final_list[changed_pinyin_index]
                tmp_pinyin = None
                p = random.random()
                if origin_initial in initial_fuzzy_dict and p < 0.8:
                    tmp_pinyin = initial_fuzzy_dict[origin_initial] + \
                                 origin_final
                elif origin_final in final_fuzzy_dict and p < 0.8:
                    tmp_pinyin = origin_initial + \
                                 final_fuzzy_dict[origin_final]
                changed_pinyin = origin_pinyin
                if tmp_pinyin and tmp_pinyin in VALID_PINYIN:
                    changed_pinyin = tmp_pinyin
                else:
                    valid_pinyins = list(VALID_PINYIN)[:]
                    random.shuffle(valid_pinyins)
                    for pinyin in valid_pinyins:
                        if PINYIN_DISTANCE_MATRIX.get((pinyin, origin_pinyin), 0) != 1:
                            continue
                        is_same_len = len(pinyin) == len(origin_pinyin)
                        if (is_same_len and is_nearby_pinyin(pinyin, origin_pinyin)) or (not is_same_len):
                            changed_pinyin = pinyin
                            break
                token_pinyin_list = pinyin_info.pinyin_list[start:end][:]
                token_pinyin_list[changed_pinyin_index -
                                  start] = changed_pinyin
            token_pinyin = ''.join(token_pinyin_list)
            before_context = text[:start]
            changed_text = None
            for google_try_time in range(3):
                try:
                    changed_text = fetch_google_input_method_result(
                        before_context, token_pinyin, token)
                    break
                except Exception as e:
                    continue
            if not changed_text or not is_chinese_string(changed_text):
                continue
            tmp_char_list = list(text)
            tmp_char_list[start:end] = list(changed_text)
            new_ppl = cal_ppl(''.join(tmp_char_list))
            ppl_improve = (new_ppl - origin_ppl) / origin_ppl * 100
            if ppl_improve > 0:
                return_char_list[start:end] = list(changed_text)
                details.append({'start': start, 'end': end,
                                'origin_token': token, 'noise_token': changed_text,
                                'pinyin_type': pinyin_type,
                                'pinyin_token': token_pinyin,
                                'ppl_improve': ppl_improve
                                })
                error_index_set.update(list(range(start, end)))
                break
    return {'origin': text, 'noise': ''.join(return_char_list), 'details': details}


def worker(sentence, q):
    result = add_noise_to_sentence(sentence)
    q.put(result)


def writer(q, pbar, batch_size, total_size, path):
    results = []
    while total_size > 0:
        result = q.get()
        results.append(result)
        total_size -= 1
        pbar.update(1)

        if len(results) >= batch_size:
            with open(path, 'a') as file:
                for r in results:
                    file.write(f"{r['noise']}\t{r['origin']}\n")
            results = []

    if results:  # 如果还有剩余的结果
        with open(path, 'a') as file:
            for r in results:
                file.write(f"{r['noise']}\t{r['origin']}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--line', type=int, default=0, help="待处理数据的初始行")
    parser.add_argument("--data-path", type=str, default="/home/jsyan/code/data_process/zikao/data/rmrb_sentence.txt",
                        help="待处理的数据文件路径")
    parser.add_argument('--batch-size', type=int, default=1000, help="每batch-size行数据写入一次文件")
    parser.add_argument("--write-path", type=str, default="/home/jsyan/code/cscd-ime/exam.txt", help="写入文件路径")
    args = parser.parse_args()
    data_path = args.data_path
    line = args.line
    write_path = args.write_path
    with open(data_path, 'r') as f:
        sentences = f.read().split('\n')
    results = []
    batch_size = 1000
    q = queue.Queue()
    sentences = sentences[line:]
    pbar = tqdm(total=len(sentences))

    writer_thread = threading.Thread(target=writer, args=(q, pbar, batch_size, len(sentences), write_path))
    writer_thread.start()

    with ThreadPoolExecutor(max_workers=64) as executor:
        futures = [executor.submit(worker, sentence, q) for sentence in sentences]
        for future in concurrent.futures.as_completed(futures):
            pass

    writer_thread.join()
    pbar.close()
