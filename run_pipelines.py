import subprocess
import os
import datetime


scripts = [
    "F:/Supermarket/pipeline_countdown.py",
    "F:/Supermarket/pipeline_newworld.py",
    "F:/Supermarket/pipeline_paknsave.py"
]

# 日志保存路径
today = datetime.datetime.today().strftime("%Y-%m-%d")
log_dir = os.path.join(os.getcwd(), "logs")
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, f"{today}.txt")

# 开始写入日志
with open(log_path, "w", encoding="utf-8") as log:
    for script in scripts:
        script_name = os.path.basename(script)
        print(f"\n👉 开始运行: {script_name}")
        log.write(f"\n👉 开始运行: {script_name}\n")

        #  运行脚本并实时输出
        process = subprocess.Popen(
            ['python', script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'  # 防止编码报错
        )

        # 实时读取输出并写入日志
        for line in iter(process.stdout.readline, ''):
            print(line, end='')         # 控制台打印
            log.write(line)             # 写入日志

        process.stdout.close()
        process.wait()

        if process.returncode != 0:
            print(f"{script_name} 执行失败，错误码: {process.returncode}")
            log.write(f"❌ {script_name} 执行失败，错误码: {process.returncode}\n")
        else:
            print(f" {script_name} 执行完成")
            log.write(f" {script_name} 执行完成\n")
