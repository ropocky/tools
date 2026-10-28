import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import openpyxl
import pandas as pd

# 创建一个线程锁，防止多线程同时打印时日志错乱
print_lock = threading.Lock()


def check_single_ip(ip, port, timeout,normal_ips):
  """单个 IP 的 SSH 检测逻辑（供线程调用）"""
  ip = ip.strip()
  if not ip:
    return None

  try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
      s.settimeout(timeout)
      s.connect((ip, port))

      # 尝试接收 SSH 服务端返回的标语 (通常形如 "SSH-2.0-OpenSSH_...")
      banner = s.recv(1024).decode("utf-8", errors="ignore").strip()

      if banner.startswith("SSH-"):
        with print_lock:
          print(f"[正常] {ip}:{port} -> SSH 服务在线 | 标语: {banner}")
          normal_ips.append((ip, banner))
      else:
        with print_lock:
          print(
              f"[异常] {ip}:{port} -> 端口开放，但返回的不是标准 SSH"
              f" 标语: {banner}"
          )
          normal_ips.append((ip, banner))

  except socket.timeout:
    with print_lock:
      print(f"[超时] {ip}:{port} -> 连接超时")
  except ConnectionRefusedError:
    with print_lock:
      print(f"[连接拒绝] {ip}:{port} -> 端口关闭或服务未启动")
  except OSError as e:
    with print_lock:
      print(f"[连接失败] {ip}:{port} -> {e}")
  except Exception as e:
    with print_lock:
      print(f"[错误] {ip}:{port} -> {e}")

  return None


def check_ssh_from_excel(file_path, port=22, timeout=3, max_workers=50):
  try:
    # 读取 Excel 文件，header=None 表示没有表头
    df = pd.read_excel(file_path, header=None)
    # 获取第一列数据，转为字符串列表并去除空值
    ips = df.iloc[:, 0].dropna().astype(str).tolist()
  except Exception as e:
    print(f"[-] 读取 Excel 文件失败: {e}")
    print(
        "提示：请确保已安装 pandas 和 openpyxl 库 (运行 pip install pandas"
        " openpyxl)"
    )
    return

  print(
      f"[+] 成功读取到 {len(ips)} 个 IP，开始多线程检测 SSH 服务 (端口:"
      f" {port}, 并发线程数: {max_workers})...\n"
  )

  normal_ips = []

  # 使用线程池并发执行检测
  with ThreadPoolExecutor(max_workers=max_workers) as executor:
    # 提交所有任务到线程池
    for ip in ips:
        executor.submit(check_single_ip, ip, port, timeout,normal_ips)


  # 打印最终结果摘要
  print("\n" + "=" * 30 + " 检测完成 " + "=" * 30)
  print(f"SSH 服务正常的 IP 列表 (总计 {len(normal_ips)} 个):")
  for ip, banner in normal_ips:
    print(f"  - {ip} -> 版本: {banner}")


if __name__ == "__main__":
  # 请将 "ips2.xlsx" 替换为你的 Excel 文件路径
  excel_file = "ips.xlsx"

  # 默认 SSH 端口是 22。如果你的 SSH 部署在其他端口，请在这里修改：
  SSH_PORT = 22

  # max_workers 代表最大并发线程数。如果 IP 很多（如几百上千个），可以适当调大（例如 50 或 100）
  check_ssh_from_excel(excel_file, port=SSH_PORT, max_workers=20)