import pandas as pd
import requests
from requests.exceptions import RequestException
import urllib3
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import openpyxl

# 禁用自签名证书警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 初始化線程鎖，用於保護多線程下的公共資源（如 print 和列表寫入）
print_lock = Lock()


def check_single_ip(ip, normal_ips):
    """
    檢測單個 IP 的函數，供線程池調用
    """
    ip = ip.strip()
    if not ip:
        return

    url = f"https://{ip}:443"

    try:
        # 发送 GET 请求，设置 3 秒超时，verify=False 忽略 SSL 证书校验
        response = requests.get(url, timeout=3, verify=False)

        # 使用線程鎖，避免多線程同時打印導致控制台畫面錯亂
        with print_lock:
            if response.status_code == 200:
                print(f"[正常] {url} -> 状态码: {response.status_code}")
                # 這裡需要記錄結果，多線程同時 append 是安全的，但加鎖更穩妥
                normal_ips.append((ip, response.status_code))
            else:
                print(f"[响应异常] {url} -> 状态码: {response.status_code}")

    except requests.exceptions.Timeout:
        with print_lock:
            print(f"[超时] {url} -> 连接超时")
    except requests.exceptions.ConnectionError:
        with print_lock:
            print(f"[连接失败] {url} -> 无法连接（端口可能关闭或服务未启动）")
    except RequestException as e:
        with print_lock:
            print(f"[错误] {url} -> {e}")


def check_ips_from_excel(file_path, max_workers=20):
    try:
        # 读取 Excel 文件
        df = pd.read_excel(file_path, header=None)
        ips = df.iloc[:, 0].dropna().astype(str).tolist()
    except Exception as e:
        print(f"[-] 读取 Excel 文件失败: {e}")
        return

    print(f"[+] 成功读取到 {len(ips)} 个 IP，開始並發檢測（最大線程數: {max_workers}）...\n")

    normal_ips = []

    # 使用 ThreadPoolExecutor 進行並發管理
    # max_workers 表示同時並發的線程數，可以根據網絡情況調整（建議 10~50 之間）
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任務到線程池
        for ip in ips:
            executor.submit(check_single_ip, ip, normal_ips)

    # 打印最终结果摘要
    print("\n" + "=" * 30 + " 检测完成 " + "=" * 30)
    print(f"访问正常的 IP 列表 (总计 {len(normal_ips)} 个):")
    for ip, code in normal_ips:
        print(f"  - {ip} (状态码: {code})")


if __name__ == "__main__":
    excel_file = "ips.xlsx"
    # 你可以通過 max_workers 參數控制並發速度
    check_ips_from_excel(excel_file, max_workers=20)
