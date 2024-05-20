#!/bin/bash

# 替换为你的程序启动命令，不包含参数
COMMAND="/data/jsyan/conda/envs/cscd/bin/python /home/jsyan/code/cscd-ime/pseudo-data-construction/build.py"

# 待处理文件路径
DATA_PATH="/data/jsyan/cscd-ime/pseudo-data-construction/data/noise_rmrb.txt"

# 目标文件路径
TARGET_FILE="/home/jsyan/code/data_process/zikao/data/noise_rmrb.txt"

# 待处理文件的行数
EXPECTED_LINES=2226600

# 检查文件行数并重启程序的函数
restart_program_with_line_count() {
    if [ -f "$TARGET_FILE" ]; then
        # 获取当前行数
        LINES=$(wc -l < "$TARGET_FILE")
        if [ $LINES -lt $EXPECTED_LINES ]; then
            # 如果行数小于预定值，使用当前行数作为参数重启程序
            echo "当前行数: $LINES，重新启动程序..."
            $COMMAND --line $LINES --write-path $TARGET_FILE --data-path DATA_PATH
            return $?
        else
            # 文件行数达到或超过预期，认为程序正常完成
            return 0
        fi
    else
        # 文件不存在，从头开始执行程序
        echo "目标文件不存在，从头开始执行程序..."
        $COMMAND --line 0 --write-path $TARGET_FILE --data-path DATA_PATH
        return $?
    fi
}

# 主循环
while true; do
    restart_program_with_line_count
    RETVAL=$?
    if [ $RETVAL -eq 0 ]; then
        echo "程序正常完成！"
        break # 跳出循环
    else
        echo "程序异常终止，正在尝试重启..."
        # 这里可以添加一些延时来避免过快重启
        sleep 1
    fi
done
