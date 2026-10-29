#sha256="cb203b72b6070f535eaff14c7c7d984cf28c58052fadf1b484f80258b07fc8c9"
#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) Huawei Technologies Co., Ltd. 2020-2030. All rights reserved.
# ----------------------------------------------------------------------------------------------------------------------
# History:
# Date                Author                      Modification
# 20200525            Author                      created file.
# ----------------------------------------------------------------------------------------------------------------------
"""
Zero Touch Provisioning (ZTP) enables devices to automatically load version files including system software,
patch files, configuration files when the device starts up, the devices to be configured must be new devices
or have no configuration files.

This is a sample of a Zero Touch Provisioning user script. You can customize it to meet the requirements of
your network environment.
"""
import http.client
import string
import re
import os
import sys
import xml.etree.ElementTree as etree
import stat
import logging
import traceback
import glob
import ops
import ipaddress

from hashlib import sha256
from urllib.request import urlretrieve
from urllib.parse import urlparse, urlunparse
from urllib.error import URLError, HTTPError, ContentTooShortError
from time import sleep, time, mktime, strptime


# ======================================================================================================================
# ZTP Python开局脚本 - 快速使用指南
#
# 一、快速修改步骤
# -----------------
# 1. 找到 "用户配置信息" 区域 (User configuration information start ~ end)
# 2. 修改 FILE_SERVER: 文件服务器地址 (必改)
# 3. 修改 TIME_SN: 时间戳标识,用于区分不同开局任务 (必改,如不需要TIME_SN校验可填空字符串)
# 4. 根据需要修改:
#    - REMOTE_IMAGE: 系统软件文件路径(.cc)
#    - REMOTE_CONFIG: 配置文件(.cfg/.zip/.dat)
#    - REMOTE_PATCH: 补丁文件(.pat)
#    - REMOTE_MOD: MOD插件文件(.mod)
#    - REMOTE_FEATURE_PLUGIN: Feature插件文件(.ccx)
#    - REMOTE_BAT: 批量执行脚本(.bat)
#    - REMOTE_LICLIST: License列表文件(.xml)
#    - REMOTE_USER: 用户自定义文件
#    - USER_COMMAND: 用户自定义命令
# 5. 注意: 文件sha256校验值,可选配置,不填则不校验
#         可使用 sha256sum filename 命令获取文件的sha256值
# 6. 保存脚本，上传到中间文件服务器
#
# 二、配置项详细说明
# ------------------
# 设置"product-name"或"uname"可以匹配同一类型的设备。
# 设置"esn"或"mac"可以精准匹配单台设备。
# 当同时设置多个时则按以下优先级查询：
#    "esn" > "mac" > "uname" > "product-name"，直到和设备匹配为止。
#
# 【product-name】产品名称 - 用于匹配设备型号
#    获取方式: display version
#    示例: Version xxx (S8700 xxx) 中的 S8700 即为 product-name
#    说明: 设备上电后会通过DHCP上报产品名称,脚本根据此字段匹配下载文件
#
# 【esn】设备ESN序列号 - 用于精准匹配单台设备
#    获取方式: display device esn
#    示例: '210235A55G10CB000001'
#    说明: 每个设备唯一的序列号,优先级最高,可实现单台设备精准开局
#    配置示例: 'esn': {'210235A55G10CB000001': {'path': '/image/S8700.cc', 'sha256': ''}}
#
# 【mac】设备MAC地址 - 用于精准匹配单台设备
#    获取方式: display bridge mac-address
#    示例: '00e0-fc12-3456'
#    说明: 设备网口MAC地址,必须与设备查询到的信息保持一致(包括大小写)
#    配置示例: 'mac': {'00e0-fc12-3456': {'path': '/image/S8700.cc', 'sha256': ''}}
#
# 【uname】设备设备名 - 用于匹配同一类型设备
#    获取方式: display version
#    示例: HUAWEI CloudEngine S8700-10 uptime is X day... 中的 CloudEngine S8700-10 即为 uname

#
# 三、匹配优先级 (从高到低)
# -------------------------
#    esn > mac > uname > product-name
#    当存在esn/mac/uname匹配时,优先使用对应的配置
#
# 四、不同开局场景配置示例
# -------------------------
# 场景1: 同一款型所有设备升级到同一版本
#    REMOTE_IMAGE = {
#        'product-name': {
#            'S8700': {'path': '/image/S8700.cc', 'sha256': ''},
#        },
#        'esn': {}, 'mac': {}, 'uname': {}
#    }
#    REMOTE_PATCH = {
#        'product-name': {
#            'S8700': {'path': '/patch/S8700.pat', 'sha256': ''},
#        },
#        'esn': {}, 'mac': {}, 'uname': {}
#    }
#    REMOTE_CONFIG = {
#        'product-name': {
#            'S8700': {'path': '/config/S8700.cfg', 'effective_mode': '0', 'save_after_success': '1'},
#        },
#        'esn': {}, 'mac': {}, 'uname': {}
#    }
#
# 场景2: 同一款型升级到不同版本
#    REMOTE_IMAGE = {
#        'product-name': {
#            'S8700': {'path': '/image/S8700.cc', 'sha256': ''},
#        },
#        'esn': {
#            '新设备ESN': {'path': '/image/S8700_new.cc', 'sha256': ''},
#        },
#        'mac': {}, 'uname': {}
#    }
#    REMOTE_PATCH = {
#        'product-name': {
#            'S8700': {'path': '/patch/S8700.pat', 'sha256': ''},
#        },
#        'esn': {
#            '新设备ESN': {'path': '/patch/S8700_new.pat', 'sha256': ''},
#        },
#        'mac': {}, 'uname': {}
#    }
#    REMOTE_CONFIG = {
#        'product-name': {
#            'S8700': {'path': '/config/S8700.cfg', 'effective_mode': '0', 'save_after_success': '1'},
#        },
#        'esn': {
#            '新设备ESN': {'path': '/config/S8700_new.cfg', 'effective_mode': '0', 'save_after_success': '1'},
#        },
#        'mac': {}, 'uname': {}
#    }
#
# 五、服务器目录结构建议
# ----------------------
#    /
#    ├── image/           # 系统软件目录 (*.cc文件)
#    ├── config/          # 配置文件目录 (*.cfg/*.zip/*.dat)
#    ├── patch/           # 补丁文件目录 (*.pat)
#    ├── license/         # License文件目录
#    │   ├── ztp_license_list.xml
#    │   └── *.dat
#    └── script/          # 脚本文件目录 (*.bat,可选)
#
# 六、报错排查指南
# ----------------
# 1. "Failed to download file xxx"
#    原因: 文件服务器连接失败或下载超时
#    检查:
#      - FILE_SERVER地址是否正确(包含http://或https://)
#      - 网络是否可达,ping服务器地址测试
#      - 用户名密码是否正确(FTP/SFTP)
#      - 服务器目录是否存在,路径是否正确

#
# 2. "sha256 check error"
#    原因: 文件SHA256校验失败
#    检查:
#      - 文件是否损坏,重新上传文件到服务器
#      - sha256字段是否为空(可忽略校验)
#      - 使用sha256sum命令重新计算文件sha256值
#
# 3. 设备信息不匹配 (file_info_list为空,无文件可下载)
#    原因: 设备信息(esn/mac/uname/product-name)与配置不匹配,get_file_infos_from_user_config返回None
#    检查:
#      - 使用display device esn获取ESN
#      - 使用display bridge mac-address获取MAC
#      - 使用display version获取product-name和uname
#      - 确认REMOTE_IMAGE/REMOTE_CONFIG中是否配置了对应信息
#      - 注意优先级: esn > mac > uname > product-name
#    相关函数: get_file_infos_from_user_config (第4739行)
#
# 4. "License active failed"
#    原因: License激活失败
#    检查:
#      - License文件是否有效,未过期
#      - License文件的ESN是否与设备ESN匹配
#      - XML文件中lic name路径是否正确
#      - LIC_DOWNLOAD_USE_XML_PATH开关设置是否正确
#
# 5. "The space is not enough"
#    原因: 设备Flash空间不足
#    检查:
#      - 删除设备上不需要的文件
#      - 配置SPACE_CLEAR清理策略
#      - 使用display device查看剩余空间
#
# 6. "Unknown file transfer scheme"
#    原因: 不支持的文件传输协议
#    检查:
#      - URL必须以sftp://、http://、ftp://、tftp://开头
#      - 检查FILE_SERVER地址格式是否正确
#
# 7. "Invalid filename" 或 "filename too long/short"
#    原因: 文件名格式错误
#    检查:
#      - 文件名不能包含特殊字符: ; & $ ` ! 等
#      - 文件名长度是否符合设备要求
#      - 文件扩展名是否正确(.cc/.cfg/.pat等)
#
# 8. "Set startup info xxx failed"
#    原因: 设置启动项失败
#    检查:
#      - 文件是否成功下载到设备

#      - 使用display startup检查启动配置
#
# 9. "Active file failed"
#    原因: 激活文件失败
#    检查:
#      - 配置文件语法是否正确
#      - 补丁文件是否与设备版本兼容
#      - 使用display patch information查看补丁状态
#
# 10. "This is a soft link file"
#    原因: 文件是软链接,设备不支持
#    检查:
#      - 将软链接替换为实际文件
#      - 确保服务器上文件为普通文件而非链接
#
# 11. "Invalid TIME_SN"
#    原因: 时间戳格式错误
#    检查:
#      - TIME_SN必须为纯数字
#      - 长度是否符合要求
#      - 避免与其他开局任务重复
#
# 七、快速修改技巧
# ----------------
# 1. 使用 "#" 注释不需要的配置项
# 2. 复制已有配置行,修改关键字段,保持格式一致
# 3. 修改前建议备份: cp ztp_script.py ztp_script.py.bak
# 4. 使用 grep -n "product-name" ztp_script.py 快速定位
#
# ======================================================================================================================

# Script configuration information start

# 非法字符集
# 特殊字符需包含 [;] [&] [$] [`] [!] [\n]
INVALID_CHARACTERS = {
    '&', '>', '<', '"', "'", "|", '`', '$', ';', '(', ')', '[', ']', '{', '}',
    '~', '*', '?', '!', '\n', '#', ',', '%', '\\'
}
INVALID_CHARACTERS_STR = ' '.join(INVALID_CHARACTERS).replace('\n', '\\n')

# error code
OK = 0
ERR = 1
# Maximum number of device startup retries when there is no query result.
GET_STARTUP_INTERVAL = 15  # The unit is second.
MAX_TIMES_GET_STARTUP = 120  # Maximum number of retries.

# Maximum number of file downloading retries.
MAX_TIMES_RETRY_DOWNLOAD = 3
MAX_TIMES_RETRY = 5
DELAY_INTERVAL = 10

# Define the file length.
FELMNAMME_120 = 120
FELMNAMME_64 = 64
FELMNAMME_4 = 4
FELMNAMME_5 = 5

# Mode for activating the device deployment file
EFFECTIVE_MODE_REBOOT       = '0'
EFFECTIVE_MODE_NO_REBOOT    = '1'
EFFECTIVE_MODE_NO_NEED      = '2'

FILE_TYPE_SOFTWARE = 'software'
FILE_TYPE_CFG   = 'cfg'
FILE_TYPE_PAT   = 'pat'
FILE_TYPE_MOD   = 'mod'
FILE_TYPE_LIC   = 'lic'
FILE_TYPE_USER  = 'user'
FILE_TYPE_FEATURE_PLUGIN = 'feature-plugin'
FILE_TYPE_PACKAGE_POOL = 'package-pool'
FILE_TYPE_SCRIPT = 'script'

HTTP_OK = [http.client.OK, http.client.CREATED, http.client.NO_CONTENT]
#日志等级
LOG_INFO_TYPE = 'INFO'
LOG_WARN_TYPE = 'WARNING'
LOG_ERROR_TYPE = 'ERROR'

# Configure the default mode for activating the deployment file.
FILE_DEFAULT_EFFECTIVE_MODE = {
    FILE_TYPE_SOFTWARE:         EFFECTIVE_MODE_REBOOT,     # cc package
    FILE_TYPE_PACKAGE_POOL:     EFFECTIVE_MODE_REBOOT,
    FILE_TYPE_CFG:              EFFECTIVE_MODE_REBOOT,     # configuration file
    FILE_TYPE_PAT:              EFFECTIVE_MODE_NO_REBOOT,  # patch
    FILE_TYPE_MOD:              EFFECTIVE_MODE_NO_REBOOT,  # mod plug-in
    FILE_TYPE_LIC:              EFFECTIVE_MODE_NO_REBOOT,  # license
    FILE_TYPE_USER:             EFFECTIVE_MODE_NO_NEED,    # User-defined file
    FILE_TYPE_FEATURE_PLUGIN:   EFFECTIVE_MODE_NO_REBOOT,  # Feature package
    FILE_TYPE_SCRIPT:           EFFECTIVE_MODE_NO_REBOOT   # Script
}

# File name extension of the deployment file, which is used for file name verification
FILE_EXTENSION = {
    FILE_TYPE_SOFTWARE:         ('.cc', ),
    FILE_TYPE_CFG:              ('.cfg', '.zip', '.dat'),
    FILE_TYPE_PAT:              ('.pat', ),
    FILE_TYPE_MOD:              ('.mod', ),
    FILE_TYPE_LIC:              ('.xml', '.dat', '.zip'),
    FILE_TYPE_FEATURE_PLUGIN:   ('.ccx', ),
    FILE_TYPE_SCRIPT:           ('.bat', ),
    FILE_TYPE_PACKAGE_POOL:     ('.zip'),
    FILE_TYPE_USER:             (None, )
}

FLASH_HOME_PATH = '{}'.format('/opt/vrpv8/home')
# Record the name of the startup information file.
STARTUP_INFO_FILE_NAME = 'ztp_startupInfo.txt'

SET_MASTER_FILE_NAME = 'ztp_master.txt'
ZTP_INSTALL_FEATURE = 'ztp_install_feature.txt'
ZTP_ENABLEFLAG = "ztp_enableFlag"
# One hour
ONEHOUR = 3600
#One minute
ONEMINUTE = 60

# ZTP status
ZTP_STATUS_RUNNING = 0
ZTP_STATUS_END = 1

# Space clearance strategy
ZTP_SPACE_CLEAR_NO_NEED     = '0' # Not cleared
ZTP_SPACE_CLEAR_NORMAL      = '1' # Common clearance (Only the software package is deleted.)
ZTP_SPACE_CLEAR_DEEP        = '2' # In-depth clearance

# List of downloaded files
ZTP_DOWNLOAD_FILE_LIST      = []

# default port
DEFAULT_PORT_FTP = 21
DEFAULT_PORT_SFTP = 22
DEFAULT_PORT_HTTP = 80

FILE_TYPE_SAVE_AFTER_SUCC = 'save_after_succ'
SAVE_AFTER_SUCC_NO = '0'  # 不执行save配置文件
SAVE_AFTER_SUCC_YES = '1' # 执行save配置文件
package_pool_flag = False
ztp_smart_load_name = None
#STACK CONFIG
STACK_ZTP = False
yang_func_ret_err = lambda ret, rsp_data: f'yang function returns {ret} and rsp_data: {rsp_data}'
yang_func_ret_success = 'SUCCESS'
# Script configuration information end
# ======================================================================================================================


# ======================================================================================================================
# User configuration information start
# ======================================================================================================================
#
# 【重要】请根据实际环境修改以下配置
# 获取设备信息命令: display version / display device esn / display bridge mac-address
#
# --------------------------------------------------------------------
# 1. 系统软件配置 (根据需要修改)
#    - path: 服务器上CC文件的路径
#    - sha256: 文件SHA256校验值(可选,不填则不校验)
#    - 获取product-name: display version 查看 Version字段中的产品名称
# --------------------------------------------------------------------
REMOTE_IMAGE = {
    'product-name': {
        'S8700' : {
            'path': '/image/software_file_name.cc',
            'sha256': '',
        },
   },
    'esn': {},
    'mac': {},
    'uname': {}
}
# --------------------------------------------------------------------
# 2. 配置文件配置 (根据需要修改)
#    - path: 服务器上配置文件路径,可用%s占位符匹配ESN/MAC
#    - effective_mode: 生效模式 (0重启生效,1不重启,2无需生效)
#    - save_after_success: 是否自动保存配置 ('0'不保存,'1'保存)
#    - 支持通配符: 'COMMON'表示所有ESN都使用该配置
#    示例: '/config/conf_%s.cfg' 会自动替换为实际ESN
# --------------------------------------------------------------------
REMOTE_CONFIG = {
    'product-name': {},
    'esn': {
        'BARCODETEST20200620' : {
            'path': '/config/conf_file_name.cfg',
            'effective_mode': EFFECTIVE_MODE_NO_REBOOT,
            'sha256': '',
	    'save_after_success': ''
        },
        'COMMON': {
            'path': '/config/conf_%s.cfg',
            'effective_mode': EFFECTIVE_MODE_NO_REBOOT,
            'sha256': '',
	    'save_after_success': ''
        }
    },
    'mac': {},
    'uname': {}
}
# --------------------------------------------------------------------
# 3. 补丁文件配置 (根据需要修改)
#    - path: 服务器上补丁文件路径(.pat文件)
# --------------------------------------------------------------------
REMOTE_PATCH = {
    'product-name': {},
    'esn': {},
    'mac': {
        '00e0-fc12-3456' : {
            'path': '/patch/pat_file_name.pat',
            'effective_mode': EFFECTIVE_MODE_NO_REBOOT,
            'sha256': '',
        },
    },
    'uname': {}
}
# --------------------------------------------------------------------
# 4. MOD插件文件配置 (根据需要修改)
#    - path: 服务器上MOD文件路径(.mod文件)
# --------------------------------------------------------------------
REMOTE_MOD = {
    'product-name': {},
    'esn': {},
    'mac': {},
    'uname': {
        'CloudEngine S8700-10': {
            'path': '/patch/mod_file_name.MOD',
            'effective_mode': EFFECTIVE_MODE_NO_REBOOT,
            'sha256': ''
        }
    }
}

# --------------------------------------------------------------------
# 5. Feature插件文件配置 (根据需要修改)
#    - path: 服务器上CCX文件路径(.ccx文件)
#    - effective_mode: 0表示重启生效
# --------------------------------------------------------------------
REMOTE_FEATURE_PLUGIN = {
    'product-name': {
        'S8700' : {
            'path': 'url_file_name.ccx',
            'effective_mode': EFFECTIVE_MODE_REBOOT,
            'sha256': '',
            },
        },
    'esn': {},
    'mac': {},
    'uname': {}
}

# --------------------------------------------------------------------
# 6. 补丁池文件配置 (根据需要修改,可选功能)
#    - path: 服务器上补丁池文件路径(.zip文件)
# --------------------------------------------------------------------
REMOTE_PACKAGE_POOL = {
    'product-name': {
        'S8700' : {
            'path': 'commonPkgPool.zip',
            'sha256': '',
        },
   },
    'esn': {},
    'mac': {},
    'uname': {}
}

# --------------------------------------------------------------------
# 7. 批量执行脚本配置 (根据需要修改,可选功能)
#    - path: 服务器上BAT脚本路径(.bat文件)
# --------------------------------------------------------------------
REMOTE_BAT = {
    'product-name': {},
    'esn': {},
    'mac': {},
    'uname': {}
}

# --------------------------------------------------------------------
# 8. License文件配置 (根据需要修改)
#    - path: 服务器上License列表文件路径(.xml文件)
#    - 详细说明见脚本头部 "License下载路径控制" 章节
#    - License列表XML格式:
#      <?xml version="1.0" encoding="utf-8" standalone="yes"?>
#      <Index formatVersion="1.0">
#          <Lic name="xxx.dat" sha256="...">
#              <LSN>xxx</LSN>
#              <Esn>设备ESN</Esn>
#          </Lic>
#      </Index>
# --------------------------------------------------------------------
REMOTE_LICLIST = {
    'path': '/license/ztp_license_list.xml',
    'sha256': 'a7638ea0a69933ac20df66ea9bf6ea301de8155684d81fbcdf00f6ca07261d7c',
}
# --------------------------------------------------------------------
# 9. 用户自定义文件配置 (根据需要修改,可选功能)
#    - path: 用户自定义文件路径
#    - sha256: 文件校验值(可选)
# --------------------------------------------------------------------
REMOTE_USER    = {
    'product-name': {},
    'esn': {
        'BARCODETEST20200620' : [
            {
                'path': '',
                'sha256': '',
            },
        ],
    },
    'mac': {},
    'uname': {}
}

# --------------------------------------------------------------------
# 10. 用户自定义命令配置 (根据需要修改,可选功能)
#     - 可在开局成功后自动执行一组CLI命令
#     - 支持多命令多设备匹配
# --------------------------------------------------------------------
USER_COMMAND = {
    'product-name': {},
    'esn': {
        'BARCODETEST2127091121312' : [
            [
                'system-view',
                'pki import-certificate default_ca realm default'
            ]
        ]
    },
    'mac': {},
    'uname': {}
}

# License下载路径控制: False-使用REMOTE_LICLIST路径+XML中lic name; True-直接使用XML中lic name
LIC_DOWNLOAD_USE_XML_PATH = False

# ======================================================================================================================
# 服务器全局配置 (必改)
# ======================================================================================================================
# FILE_SERVER: 文件服务器地址
#    支持格式:
#    - 选择sftp服务器: sftp://username:password@hostname:port 或 sftp-sha1://username:password@hostname:port
#    - 选择http服务器: http://hostname:port (无用户名密码) 或 http://username:password@hostname:port
#    - 选择tftp服务器: tftp://hostname
#    - 选择ftp服务器: ftp://username:password@hostname:port
#    - 选择本地文件服务器: file://filepath (U盘开局场景，从U盘下载开局文件)
#    注意: 路径末尾不要带斜杠
FILE_SERVER         = 'sftp://sftp_user:sftp_pwd@xx.xx.xx.xx'

# ======================================================================================================================
# 其他全局配置 (根据需要修改)
# ======================================================================================================================
# TIME_SN: 时间戳标识,用于区分不同开局任务
#    格式: YYYYMMDDHHmmss
#    说明: 同一设备重复开局需修改此值
TIME_SN             = '20200526120159'

# SYSLOG_INFO: 日志服务器配置
#    格式: 'UDP' 或 'TCP'
#    说明: 设备开局过程中的日志会发送到日志服务器
SYSLOG_INFO         = 'UDP'

# SPACE_CLEAR: Flash空间清理策略
#    ZTP_SPACE_CLEAR_NO_NEED ('0'): 不清理 (默认)
#    ZTP_SPACE_CLEAR_NORMAL ('1'): 普通清理 (仅删除软件包)
#    ZTP_SPACE_CLEAR_DEEP ('2'): 深度清理 (删除所有非开局文件)
SPACE_CLEAR         = ZTP_SPACE_CLEAR_NO_NEED

# ACTIVE_DELAYTIME: 文件激活延时时间(秒)
#    例: '60' 表示开局完成后60秒再激活
ACTIVE_DELAYTIME    = '60'

# ACTIVE_INTIME: 文件定时激活时间
#    格式: 'HH:MM' 例如 '23:59'
#    说明: 与ACTIVE_DELAYTIME二选一,优先使用此配置
ACTIVE_INTIME       = None

# VRPVER: 软件版本号(可选,用于验证)
VRPVER              = None

# INSTALL_WEAK: 是否安装弱功能Feature包
#    1: 安装  0: 不安装  None: 不处理
INSTALL_WEAK        = None

# DHCP_TYPE: DHCP协议版本
#    'DHCPv4': 使用IPv4 DHCP (默认)
#    'DHCPv6': 使用IPv6 DHCP
DHCP_TYPE = 'DHCPv4'
# SSH and HTTP post device info configuration information start

# SSH configuration
AAA_USER = "useradmin" # Admin user
AAA_PASSWORD = "YsHsjx_202206"  # Admin password
CON_PASSWORD = "YsHsjx_202206" # Console password
SAVE_CONFIG_FILENAME = "vrpconf.cfg" # Save configuration file name

# To use ZTP config ssh function, set ssh_login_config to True.
# ssh_login_config will be treated as false if the deployment file is configured in REMOTE_CONFIG.
ssh_login_config = False

# If HTTP_POST_SWITCH is set to True, ZTP uses the http post method to send the HTTP_POST_HEADER and HTTP_POST_BODY information
# to the HTTP server specified by HTTP_POST_URL.HTTP_POST_URL supports domain names and IP addresses.
HTTP_POST_SWITCH = False

HTTP_POST_URL = 'http://120.63.64.112:8888'
HTTP_POST_HEADER = 'Content-Type:application/json'
# target
HTTP_POST_BODY = {"target":"",
                "sshType":"HOS",
                "script":"ztpService",
                "switchPort":"",
                "Esn":"",
                "Mac":"",
                "hwType":"",
                "hwVersion":"",
                "eventType":"phase1"
                }

# SSH and HTTP post device info configuration information end

# User configuration information end
# ======================================================================================================================

# OPS objects
slog = ops.ops()
# Log file name
LOG_FILE = ''
# python file name
PYTHON_FILE = os.path.basename(__file__)

SYSTEM_FILE_INIT = 0
SYSTEM_FILE_SETTING_END = 1
system_file_state = SYSTEM_FILE_INIT

SYSTEM_STARUPINFO_INIT = 0
SYSTEM_STARUPINFO_END = 1
system_startupInfo_state = SYSTEM_STARUPINFO_INIT

system_reboot_needed = True

SFTP_DEFAULT_PORT = 22
FTP_DEFAULT_PORT = 21
HTTP_DEFAULT_PORT = 80

SET_SOFTWARE = 'SET_SOFTWARE'
SET_CFG = 'SET_CFG'
SET_PATCH = 'SET_PATCH'
SET_MOD_PATCH = 'SET_MOD_PATCH'
SET_FEATURE_PLUGIN = 'SET_FEATURE_PLUGIN'
TIMES_STARTUP_RETRY = 60
DELAY_INTERVAL_SET_INFO = 2

CLI_TYPE_YANG = 'YANG'

install_weakea_feature = None
is_set_master = None
is_clear_master = False
master_exportcfg = None
flash_home_path_master = None
flash_home_path_slave = None
usb_home_path = None
g_is_usb_startup = False
# ZTP enable/disable status
ZTP_STATUS_DISABLE = 'false'

item_str = lambda key, value: f'<{key}>{value}</{key}>'

log_info_dict = {LOG_INFO_TYPE: logging.info,
                 LOG_WARN_TYPE: logging.warning,
                 LOG_ERROR_TYPE: logging.error}
ZTP_CLAER_ADD_SPACE = 40000

class OPIExecError(Exception):
    """OPI executes error."""
    pass


class ZTPErr(Exception):
    """ZTP error."""
    pass


class ExecFileErr(Exception):
    """Execute file error."""
    pass


class ZTPAbort(Exception):
    """Abort ZTP automatically."""
    pass

class ZTPTimesnRepeat(Exception):
    """Time SN Repeat."""
    pass

class ZTPRollback(Exception):
    """ZTP startup info rollback."""
    pass

class ZTPDisableAbort(Exception):
    """
    The user executed set ztp disable.
    """
    pass

def ops_conn_operation(func):
    def wapper(*args, **kwargs):
        ops_conn = ops.OPSConnection("localhost")
        kwargs.update({"ops_conn": ops_conn})
        try:
            ret = func(*args, **kwargs)
            return ret
        except OPIExecError as reason:
            raise OPIExecError(reason)
        except Exception as reason:
            exception_info = \
                "{} failed, reason = {}".format(func.__name__, reason)
            raise Exception(exception_info)
        finally:
            ops_conn.close()

    return wapper


def print_ztp_log(ztp_info, log_type):
    """
    ztp日志打印:串口打印日志、logging日志
    """
    log_info_dict.get(log_type)(ztp_info)
    log_level = log_type.upper()
    slog.terminal.write(f"\n{log_level}:{ztp_info}", None, fgrd = True)


def execute_cli(ops_obj, handle, cli_info):
    ret, _, result = ops_obj.cli.execute(handle, cli_info)
    if ret is None:
        print_ztp_log(f"Execute cli '{cli_info}' failed, result={result}", LOG_ERROR_TYPE)
        return False
    return True


def cli_operation_x(func):
    def wapper(*args, **kwargs):
        ops_obj = ops.ops()
        ops_obj.set_model_type('YANG')
        handle, result = ops_obj.cli.open()
        if handle is None or result != "Success":
            return False, result
        kwargs.update({"ops_obj": ops_obj})
        kwargs.update({"handle": handle})
        try:
            return func(*args, **kwargs)
        except Exception as reason:
            return False, str(reason)
        finally:
            ret, result = ops_obj.cli.close(handle)
            if ret:
                logging.warning(f"Failed to close cli channel, handle = {handle}, ret={ret}.")

    return wapper


@cli_operation_x
def set_aaa_password(ops_obj=None, handle=None):
    cli_list = ["return", "system-view", "aaa", f"local-user {AAA_USER} password irreversible-cipher {AAA_PASSWORD}", f"local-user {AAA_USER} service-type ssh", f"local-user {AAA_USER} privilege level 3",f"local-user {AAA_USER} password-force-change disable"]
    for cli_info in cli_list:
        if not execute_cli(ops_obj=ops_obj, handle=handle, cli_info=cli_info):
            return False
    print_ztp_log("Set aaa password success.", LOG_INFO_TYPE)
    return True

@cli_operation_x
def set_aaa_privilege(ops_obj=None, handle=None):
    cli_list = ["return", "system-view", "aaa", f"local-user {AAA_USER} privilege level 3"]
    for cli_info in cli_list:
        if not execute_cli(ops_obj=ops_obj, handle=handle, cli_info=cli_info):
            return False
    print_ztp_log("Set aaa privilege success.", LOG_INFO_TYPE)
    return True

@cli_operation_x
def set_screen_length_to_unlimit(ops_obj=None, handle=None):
    cli_list = ["system-view", "user-interface vty 0 4", "screen-length 0"]
    for cli_info in cli_list:
        if not execute_cli(ops_obj=ops_obj, handle=handle, cli_info=cli_info):
            return False
    print_ztp_log("Set screen length to un limit success.", LOG_INFO_TYPE)
    return True

@cli_operation_x
def set_con_password(ops_obj=None, handle=None):
    cli_list = ["return", "system-view", "user-interface con 0", "authentication-mode password", f"set authentication password cipher {CON_PASSWORD}"]
    for cli_info in cli_list:
        if not execute_cli(ops_obj=ops_obj, handle=handle, cli_info=cli_info):
            return False
    print_ztp_log("Set con password success.", LOG_INFO_TYPE)
    return True

@cli_operation_x
def set_sha1_enable(ops_obj=None, handle=None):
    cli_list = ["return", "system-view", "ssh server publickey rsa_sha2_256 rsa_sha2_512 rsa"]
    for cli_info in cli_list:
        if not execute_cli(ops_obj=ops_obj, handle=handle, cli_info=cli_info):
            return False
    print_ztp_log("Set ssh sha1 enable success.", LOG_INFO_TYPE)
    return True


@ops_conn_operation
def set_stelnet_server_enable(ops_conn=None):
    """ stelnet enable """
    uri = "/restconf/data/huawei-sshs:sshs/server-enable"
    req_data = """<server-enable>
                <stelnet-ipv6-enable>enable</stelnet-ipv6-enable>
                <stelnet-ipv4-enable>enable</stelnet-ipv4-enable>
                </server-enable>
            """
    ret, _, rsp_data = ops_conn.set(uri, req_data)
    if ret not in HTTP_OK:
        print_ztp_log(f"Enable stelnet server failed, ret={ret}, rsp_data={rsp_data}", LOG_ERROR_TYPE)
        return False
    print_ztp_log(f"Enable stelnet server success", LOG_INFO_TYPE)
    return True


@cli_operation_x
def clear_interface_desc(ifname, ops_obj=None, handle=None):
    cli_list = ["system-view", f"interface {ifname}", "undo description"]
    for cli_info in cli_list:
        if not execute_cli(ops_obj=ops_obj, handle=handle, cli_info=cli_info):
            print_ztp_log(f"Clear interface {ifname} description failed.", LOG_INFO_TYPE)
            return False
    print_ztp_log(f"Clear interface {ifname} description success.", LOG_INFO_TYPE)
    return True


@ops_conn_operation
def get_ztp_status_flag(ops_conn=None):
    """
    获取ztp使能/去使能标志
    """

    uri = '{}'.format('/restconf/data?fields=/huawei-sztp:sztp/get-ztp-status-flag(statusflag)')
    req_data = None
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ret == http.client.NOT_FOUND:  # 404 变量还未创建
        return ERR, 'NOT FOUND'
    if ops_return_result(ret) or rsp_data == '':
        return ERR, yang_func_ret_err(ret, rsp_data)
    return OK, rsp_data


def ztp_status_flag_get():
    """
    Obtain the ZTP enable/disable status.
    """
    ret, rsp_data = get_ztp_status_flag()
    if ret == ERR:
        if rsp_data == 'NOT FOUND':
            return ERR, 'Can not found ztp_statusFlag.'
        return ERR, 'Failed to get the value of ztp_statusFlag.'
    root_elem = etree.fromstring(rsp_data)
    namespaces = {'sztp': 'urn:huawei:yang:huawei-sztp'}
    elem = root_elem.find('sztp:sztp/sztp:get-ztp-status-flag/sztp:statusflag', namespaces)
    if elem is None:
        return ERR, 'Failed to get the value of ztp_statusFlag for none element'
    return OK, elem.text


def check_ztp_status_is_disable():
    """
    检测当前设备用户是否下发了set ztp disable
    """

    ret, ztp_status = ztp_status_flag_get()

    if ret != OK:
        return False

    if ztp_status == str(ZTP_STATUS_DISABLE):
        return True

    return False


@ops_conn_operation
def ssh_server_source_all_interface(ops_conn=None):
    uri = "/restconf/data/huawei-sshs:sshs/all-server-source"
    req_data = """<all-server-source>
                    <all-ipv4-interface>true</all-ipv4-interface>
                    <all-ipv6-interface>true</all-ipv6-interface>
                    </all-server-source>
                """
    ret, _, rsp_data = ops_conn.set(uri, req_data)
    if ret not in HTTP_OK:
        print_ztp_log(f"Config ssh server source failed, ret={ret}, rsp_data={rsp_data}", LOG_ERROR_TYPE)
        return False
    print_ztp_log("Ssh server source has configed.", LOG_INFO_TYPE)
    return True


@ops_conn_operation
def set_startup_config_file(file_path, exportcfg=None, ops_conn=None):
    """ Set the next startup saved-configuration file """

    uri = '/restconf/operations/huawei-cfg:set-startup'
    req_data = ''
    if exportcfg is not None:
        exportcfg_change = ops.opscharacterEncode(exportcfg)
        items = {'filename': file_path, 'shareable-mode': 'password', 'password': exportcfg_change}
    else:
        items = {'filename': file_path, 'shareable-mode': 'default'}

    for key in items.keys():
        req_data = '{}{}'.format(req_data, item_str(key, items[key]))

    req_data = item_str('input', req_data)
    ret, _, rsp_data = ops_conn.create(uri, req_data)
    if ops_return_result(ret):
        print_ztp_log("Set the next startup saved-configuration failed", LOG_ERROR_TYPE)
        return ERR
    print_ztp_log("Set the next startup saved-configuration success", LOG_INFO_TYPE)
    return OK


@ops_conn_operation
def save_config_file(cfg_name='vrpcfg.zip', ops_conn=None):
    """ Save the current configuration to file """

    uri = '/restconf/operations/huawei-cfg:save'
    req_template = string.Template('''
        <input>
            <filename>$cfgname</filename>
        </input>
        ''')
    req_data = req_template.substitute(cfgname=cfg_name)
    ret, _, rsp_data = ops_conn.create(uri, req_data)
    if ops_return_result(ret):
        print_ztp_log("Save the current configuration to file failed", LOG_ERROR_TYPE)
        return ERR
    print_ztp_log("Save the current configuration to file success", LOG_INFO_TYPE)
    return OK

def disable_ssh_login_config():
    global ssh_login_config
    if ssh_login_config:
        ssh_login_config = False
        print_ztp_log("Change the value of ssh_login_config to False,"
                      "because the deployment file contains configuration files.", LOG_WARN_TYPE)


def set_ssh_network_config():
    global ssh_login_config
    if not ssh_login_config:
        return
    print_ztp_log("Begin config ssh.", LOG_INFO_TYPE)
    # step1 telnet_enable
    if not set_stelnet_server_enable():
        print_ztp_log("Enable stelnet server failed.", LOG_ERROR_TYPE)
    if not ssh_server_source_all_interface():
        print_ztp_log("Ssh server source all interfaces failed", LOG_ERROR_TYPE)
    # step4 Setting the AAA User
    if not set_aaa_password():
        print_ztp_log("Add aaa user failed failed", LOG_ERROR_TYPE)
    set_aaa_privilege()
    if not set_screen_length_to_unlimit():
        print_ztp_log("Set screen length failed", LOG_ERROR_TYPE)
    if not set_con_password():
        print_ztp_log("Set con password failed", LOG_ERROR_TYPE)
    set_sha1_enable()
    clear_interface_desc("Vlanif1")
    save_config_file(SAVE_CONFIG_FILENAME)
    set_startup_config_file(SAVE_CONFIG_FILENAME)
    print_ztp_log("save currnet config", LOG_INFO_TYPE)
    sleep(5)
    return


@ops_conn_operation
def yang_get_interface_ip(ifname, ops_conn=None):
    """ Get the interface ip information """

    if_name = ifname.replace('/', '%2F')
    uri = '{}'.format(f'/restconf/data/huawei-ifm:ifm/interfaces/interface={if_name}/huawei-ip:ipv4/state/addresses')
    req_data = None
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ops_return_result(ret) or ret == http.client.NOT_FOUND:  # 404 无数据
        return ERR, ""
    return OK, rsp_data


def get_interface_ip(if_name):
    """ Get the interface ip information """

    print_ztp_log(f"Get interface {if_name} info.", LOG_INFO_TYPE)
    ret, rsp_data = yang_get_interface_ip(ifname=if_name)
    if ret == ERR:
        return None, None

    root_elem = etree.fromstring(rsp_data)
    namespaces = {'ipv4': 'urn:huawei:yang:huawei-ip'}
    for address in root_elem.findall('ipv4:address', namespaces):
        ip_addr = address.find("ipv4:ip", namespaces)
        if ip_addr is None:
            break
        mask = address.find("ipv4:mask", namespaces)
        if mask is None:
            break
        print_ztp_log(f'Get interface {if_name} ip allocated.', LOG_INFO_TYPE)
        return ip_addr.text, mask.text
    return None, None


def get_val_from_system_info(key, system_info):
    key = key.lower()
    if key == 'switchport':
        return 'Vlanif1'
    elif key == 'hwtype':
        return system_info.get('product-name', '')
    elif key == 'target':
        ip_addr, mask = get_interface_ip("Vlanif1")
        return ip_addr
    elif key == 'hwversion':
        return system_info.get('product-version', '')
    elif key == 'esn':
        return system_info.get('esn', '')
    elif key == 'mac':
        return system_info.get('mac', '')
    else:
        print_ztp_log(f'The key {key} you need to manually assign a value to HTTP_POST_BODY.', LOG_ERROR_TYPE)
        return ''
    return ''

def device_info_to_json():
    if not isinstance(HTTP_POST_BODY, dict):
        print_ztp_log('HTTP_POST_BODY format error.Please check.', LOG_ERROR_TYPE)
        return ''
    system_info = get_system_info()
    json_string = '{'
    for key, v in HTTP_POST_BODY.items():
        if v == '':
            v = get_val_from_system_info(key, system_info)
        temp = string.Template('"$key":"$v"')
        temp = temp.substitute(key=key, v=v)
        json_string = json_string + temp + ','

    json_string = json_string[:-1] + '}'
    return json_string


@ops_conn_operation
def http_post_device_info(ops_conn=None):
    if not HTTP_POST_SWITCH:
        return OK
    json_data = device_info_to_json()
    uri = '{}'.format('/restconf/operations/huawei-http-inner:httpc-sendrequest/')
    str_temp = string.Template('''
        <input>
            <method>$method</method>
            <url>$url</url>
            <header>$header</header>
            <body>$body</body>
            <client-timeout>$timeout</client-timeout>
        </input>
    ''')
    req_data = str_temp.substitute(method='POST',
                                   url=HTTP_POST_URL,
                                   header=HTTP_POST_HEADER,
                                   body=json_data,
                                   timeout=60)
    ret, _, rsp_data = ops_conn.create(uri, req_data)
    if ops_return_result(ret) or ret == http.client.NOT_FOUND:
        print_ztp_log("Failed to post information to server.", LOG_ERROR_TYPE)
    else:
        print_ztp_log("Succeed to post information to server.", LOG_INFO_TYPE)
    return OK


def cli_operation(func):
    def wapper(*args, **kwargs):
        ops_obj = ops.ops()
        ops_obj.set_model_type(CLI_TYPE_YANG)
        handle, result = ops_obj.cli.open()
        if handle is None or result != "Success":
            return ERR, result
        kwargs.update({"ops_obj": ops_obj})
        kwargs.update({"handle": handle})
        try:
            return func(*args, **kwargs)
        except Exception as reason:
            return ERR, str(reason)
        finally:
            ret, result = ops_obj.cli.close(handle)
            if ret != OK:
                logging.warning(f"Failed to close cli channel, handle = {handle}.")
    return wapper


class cli():
    """ 命令行操作 """

    @staticmethod
    @cli_operation
    def patch_delete_all(ops_obj=None, handle=None):
        ops_obj.cli.execute(handle, "return")
        choice = {"[Y/N]": "y"}
        ret, _, result = ops_obj.cli.execute(handle, f'patch delete all', choice)
        if ret is None:
            return ERR, result
        return OK, ret

    @staticmethod
    @cli_operation
    def reset_next_feature_plugin(file_path, ops_obj=None, handle=None):
        ops_obj.cli.execute(handle, "return")
        ret, _, result = ops_obj.cli.execute(handle, f'reset feature-software next-startup {file_path}')
        if ret is None:
            return ERR, result
        return OK, ret

    @staticmethod
    @cli_operation
    def rollback_cfg_to_file(file_name, ops_obj=None, handle=None):
        ops_obj.cli.execute(handle, "return")
        ret, _, result = ops_obj.cli.execute(handle, f'rollback configuration to file {file_name}')
        if ret is None:
            return ERR

        if 'fail' in ret:
            print_ztp_log("several configurations failed to be configed to device.", LOG_ERROR_TYPE)
            ret, _, result = ops_obj.cli.execute(handle, 'display configuration rollback result')
            print_ztp_log(f"The execution result of {file_name} is as follows, The result is obtained by running the "
                f"display configuration rollback result command.\n{ret}", LOG_WARN_TYPE)
        return OK

    @staticmethod
    @cli_operation
    def execute_bat_file(file_name, ops_obj=None, handle=None):
        ops_obj.cli.execute(handle, "return")
        ops_obj.cli.execute(handle, "system-view")
        ret, _, result = ops_obj.cli.execute(handle, f"execute {file_name}")
        if ret is None:
            return ERR, result
        return OK, ret

    @staticmethod
    @cli_operation
    def execute_cli_list(cli_list, ops_obj=None, handle=None):
        for cli in cli_list:
            ret, _, result = ops_obj.cli.execute(handle, cli)
            if ret is None:
                return ERR, result
        return OK, OK




def ops_return_result(ret):
    return ((ret != http.client.OK) and \
            (ret != http.client.CREATED) and \
            (ret != http.client.NO_CONTENT))



@ops_conn_operation
def file_exist_on_slave(file_path='', ops_conn=None):

    file_dir, file_name = os.path.split(file_path)
    file_dir = file_dir + "/"
    file_dir = file_dir.replace('/', '%2F')
    uri = '{}'.format(f'/restconf/data/huawei-file-operation:file-operation/dirs/dir={file_name},{file_dir}')
    req_data = None
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ops_return_result(ret) or rsp_data == '':
        return False
    return True

@ops_conn_operation
def get_home_path(ops_conn=None):
    """ Get the full filename of the home directory """
    uri = '{}'.format('/restconf/data/huawei-file-operation:file-operation/disk-usages')
    req_data = None
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ops_return_result(ret) or rsp_data == '':
        logging.error('Failed to get the current working directory.')
        raise OPIExecError('Failed to get the home directory.')

    root_elem = etree.fromstring(rsp_data)
    namespaces = {'file-operation': 'urn:huawei:yang:huawei-file-operation'}
    usb_dirs = []
    slave_dir_list = []
    master_dir = None
    for disk_usage in root_elem.findall('file-operation:disk-usage', namespaces):
        elem = disk_usage.find("file-operation:path", namespaces)
        if elem is None or elem.text is None:
            continue
        if elem.text.lower().find('usb') >= 0:
            usb_dirs.append(elem.text)
        else:
            if elem.text.lower().startswith('flash'):
                master_dir = elem.text
            else:
                slave_dir_list.append(elem.text)
    usb_dirs.sort(reverse=True)
    return master_dir, slave_dir_list, usb_dirs


@ops_conn_operation
def file_exist_on_master(file_path='', ops_conn=None):
    home_dir, _, _ = get_home_path()
    if home_dir is None:
        logging.error("Failed to get the home directory.")
        return False
    if file_path.startswith(home_dir):
        file_path_real = file_path
    else:
        file_path_real = os.path.join(home_dir, file_path)

    file_dir, file_name = os.path.split(file_path_real)
    if file_dir == home_dir:
        # Run the glob module to query the file in the root directory of the flash memory.
        file_path_real = file_path_real.replace(home_dir, FLASH_HOME_PATH, 1)
        file_list = glob.glob(file_path_real)
        return True if len(file_list) > 0 else False
    else:
        # Invoke the YANG interface if the file is not in the root directory of the flash memory.
        file_dir = file_dir + "/"
        file_dir = file_dir.replace('/', '%2F')
        uri = '{}'.format(f'/restconf/data/huawei-file-operation:file-operation/dirs/dir={file_name},{file_dir}')
        req_data = None
        ret, _, rsp_data = ops_conn.get(uri, req_data)
        if ops_return_result(ret) or rsp_data == '':
            return False
        return True


def file_exist(file_path=''):
    """ 判断主控板上某文件是否存在 """

    if file_path is None or file_path == '':
        logging.warning("The path of file is none or ''.")
        return ERR

    if file_path.lower().startswith('flash'):
        return file_exist_on_master(file_path)
    else:
        return file_exist_on_slave(file_path)


@ops_conn_operation
def file_delete(file_path='', ops_conn=None):
    if file_path is None or file_path == '':
        logging.warning("The path of file is none or ''.")
        return ERR

    if not file_exist(file_path):   # file not exist
        return OK

    logging.info(f"Delete file '{file_path}' permanently...")
    uri = '{}'.format('/restconf/operations/huawei-file-operation:delete-file')
    req_template = string.Template('''
        <input>
            <file-name>$filePath</file-name>
            <delete-type>$deleteType</delete-type>
        </input>
        ''')
    req_data = req_template.substitute(filePath=file_path, deleteType="unreserved")
    ret, _, _ = ops_conn.create(uri, req_data)
    if ops_return_result(ret):
        logging.error('Failed to delete the file.')
        return ret

    logging.info("Delete the file successfully.")
    return OK



def file_delete_on_MPUs(file_path='', slave=0):
    if file_path:
        file_name = os.path.basename(file_path)
        home_path_master, home_path_slave, _= get_home_path()
        ret = file_delete(file_path=os.path.join(home_path_master, file_name))
        if ret != OK:
            return ret
        if slave:   # 存在备用主控板，继续删除备用主控板上的文件
            for slave_path in home_path_slave:
                ret = file_delete(file_path=os.path.join(slave_path, file_name))
                if ret != OK:
                    return ret
    return OK


def del_list_file(files_list, exclude_file_list):
    """ 删除指定list文件的所有的文件 """
    for key in files_list.keys():
        for filename in files_list.get(key):
            if filename != exclude_file_list:
                file_delete(os.path.join(key, filename))


@ops_conn_operation
def copy_file(src_path='', dest_path='', ops_conn=None):
    """Copy a file.

    The value of src_path and dest_path can be in the format of filename,
    flash:/filename, and flash:/xxx/filename.
    """
    logging.info('Copy file {} to {}...'.format(src_path, dest_path))
    uri = '{}'.format('/restconf/operations/huawei-file-operation:copy-file')
    str_temp = string.Template('''\
<input>
    <src-file-name>$src</src-file-name>
    <des-file-name>$dest</des-file-name>
</input>
''')
    req_data = str_temp.substitute(src=src_path, dest=dest_path)
    ret, _, _ = ops_conn.create(uri, req_data)
    if ops_return_result(ret):
        logging.error('Copy file failed.')
        return ERR
    return OK


def get_file_list_cur(types=0):
    filelist = []
    fileNames = glob.glob(FLASH_HOME_PATH + r"/*.*")
    try:
        for fileName in fileNames:
            name = os.path.basename(fileName)
            filelist.append(name)
    except Exception as reason:
        logging.error("Failed to get file list! reason = {} ".format(reason))
        return filelist

    return filelist


@ops_conn_operation
def get_file_list(file_dir='', ops_conn=None):
    """Obtain the file list. """
    file_list = []
    home_dir, _, _ = get_home_path()
    if home_dir == file_dir:
        file_list = get_file_list_cur()
        return file_list

    if not file_dir.endswith('/'):
        file_dir = '{}{}'.format(file_dir, '%2F')
    file_dir = file_dir.replace('/', '%2F')

    uriTmp = '{}'.format('/restconf/data/huawei-file-operation:file-operation/dirs/dir=')
    uri = '{}{}{}'.format(uriTmp, ',', file_dir)
    req_data = None
    try:
        ret, _, rsp_data = ops_conn.get(uri, req_data)
        if ops_return_result(ret) or rsp_data == '':
            logging.error('Failed to get file list')
            return file_list
    except Exception as e:
        logging.warning(f'{e}')
        return file_list

    rsp_data1=rsp_data.replace('<?xml version="1.0" encoding="UTF-8"?>','')
    rsp_data1=rsp_data1.replace('xmlns="urn:huawei:yang:huawei-file-operation"','')
    rsp_data = '{}{}{}'.format('<dirs>',rsp_data1,'</dirs>')

    root_elem = etree.fromstring(rsp_data)
    namespaces = {'file-operation': 'urn:huawei:yang:huawei-file-operation'}
    mpath = '{}'.format('dir')
    for file_tmp in root_elem.findall(mpath, namespaces):
        file_name = file_tmp.find("file-name", namespaces)
        elem = file_tmp.find("dir-name", namespaces)
        if elem is None or file_name is None:
            continue
        _, part2 = os.path.splitext(file_name.text)
        if part2 != '':
            file_list.append(file_name.text)
    return file_list


@ops_conn_operation
def get_file_size_form_dir(file_path='', file_dir='', ops_conn=None):
    """Return the size of a file in the directory under the home directory. """
    file_size = 0
    src_file_name = os.path.basename(file_path)
    uriTmp = '{}'.format('/restconf/data/huawei-file-operation:file-operation/dirs/dir=')
    uri = '{}{}{}{}'.format(uriTmp, src_file_name, ',', file_dir)
    req_data = None
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ops_return_result(ret) or rsp_data == '':
        return file_size
    else:
        root_elem = etree.fromstring(rsp_data)
        namespaces = {'file-operation': 'urn:huawei:yang:huawei-file-operation'}
        uriTmp = '{}'.format('/size')
        uriTmp = uriTmp.replace('/', '/file-operation:')
        mpath = uriTmp[1:]
        elem = root_elem.find(mpath, namespaces)
        if elem is None:
            return file_size
        file_size = int(elem.text.encode('utf-8').decode('utf-8')) / 1024
        return file_size


@ops_conn_operation
def smart_download_package(req_data, ops_conn=None):
    """ smart load package """

    uri = '/restconf/operations/huawei-software:smart-load-package'
    ret, _, rsp_data = ops_conn.create(uri, req_data)
    if ops_return_result(ret):
        return ERR, yang_func_ret_err(ret, rsp_data)
    return OK, yang_func_ret_success


@ops_conn_operation
def get_smart_load_package_result(ops_conn=None):
    """ Set the next startup system software """

    uri = '{}'.format(f'/restconf/data/huawei-software:software/smart-load-package-result')
    req_data = None
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ops_return_result(ret):
        return ERR, yang_func_ret_err(ret, rsp_data)
    return OK, rsp_data

def get_file_size_cur(file_path=''):

    file_size = 0
    if file_path == '' or file_path == None:
        return file_size

    src_file_name = os.path.basename(file_path)
    fileName = '{}{}{}'.format(FLASH_HOME_PATH, '/', src_file_name)
    try:
        fileinfo = os.stat(fileName)
        file_size = int(fileinfo.st_size) / 1024
        return file_size
    except Exception as reason:
        print_ztp_log(f"Get file size failed. reason = {reason}", LOG_ERROR_TYPE)
        return file_size


def get_file_size(file_path=''):
    """Return the size of a file in the home directory."""
    if file_path == '' or (file_path is None):
        return 0
    home_dir, _, _ = get_home_path()
    file_dir, _ = os.path.split(file_path)
    if home_dir == file_dir:
        return get_file_size_cur(file_path)

    cwd, file_name = os.path.split(file_path)
    file_dir = '{}{}'.format(cwd, '%2F')
    file_dir = file_dir.replace('/', '%2F')

    size = get_file_size_form_dir(file_path=file_name, file_dir=file_dir)

    return size

def create_sftp_smart_load_req(req_params, type):
    req_str = '{}'.format(f'''
        <input>
            <file-name>$fileName</file-name>
            <sftp-server-ip-version>$type</sftp-server-ip-version>
            <sftp-server>$serverIp</sftp-server>
            <sftp-user-name>$userName</sftp-user-name>
            <sftp-password>$password</sftp-password>
            <sftp-port>$serverPort</sftp-port>
        </input>
        ''')
    req_template = string.Template(req_str)
    req_data = req_template.substitute(serverIp=req_params.get('ip'),
                                        serverPort=req_params.get('port'),
                                        userName=req_params.get('username'),
                                        password=req_params.get('password'),
                                        fileName=req_params.get('filename'),
                                        type=type)
    return req_data

@ops_conn_operation
def _sftp_download_file_yang(ops_conn=None, url='', local_path=''):
    """Download files using SFTP.

    Args:
        url: URL of a remote file, for example, sftp://sftp_user:sftp_pwd@xx.xx.xx.xx:port/test/vrpcfg.cfg
        local_path: The path must start with the root directory flash:, for example, flash:/vrpcfg.cfg or vrpcfg.cfg.
    """
    print_ztp_log(f'SFTP download {os.path.basename(url)} to {local_path}.', LOG_INFO_TYPE)
    uri = '{}'.format('/restconf/operations/huawei-sshc:ssh-transfer-file')
    str_temp = string.Template('''\
<input>
    <server-port>$serverPort</server-port>
    <host-addr-ipv4>$serverIp</host-addr-ipv4>
    <command-type>get</command-type>
    <user-name>$username</user-name>
    <password>$password</password>
    <local-file-name>$localPath</local-file-name>
    <remote-file-name>$remotePath</remote-file-name>
</input>
''')
    global ztp_smart_load_name
    url_tuple = urlparse(url)
    if re.match(r"\d+\.\d+\.\d+\.\d+", url_tuple.hostname):
        server_ip = url_tuple.hostname
    else:
        server_ip = get_addr_by_hostname(host=url_tuple.hostname)
    global sftp_server
    sftp_server = server_ip
    if url_tuple.port == None:
        server_port = SFTP_DEFAULT_PORT
    else:
        server_port = url_tuple.port
    req_data = str_temp.substitute(serverIp=server_ip,
                                   serverPort=server_port,
                                   username=url_tuple.username,
                                   password=url_tuple.password,
                                   remotePath=url_tuple.path[1:],
                                   localPath=local_path)
    req_params = {}.fromkeys(('ip', 'port', 'username', 'password', 'path', 'filename'))
    req_params['ip'] = server_ip
    req_params['port'] = url_tuple.port if url_tuple.port is not None else SFTP_DEFAULT_PORT
    req_params['username'] = url_tuple.username
    req_params['password'] = url_tuple.password
    req_params['path'] = url_tuple.path[1:]
    req_params['filename'] = os.path.basename(url)
    try:
        if package_pool_flag:
            # 构造入参
            req_data = create_sftp_smart_load_req(req_params, 'ipv4')
            # print_ztp_log(f'SFTP smart download req_data {req_data}.', LOG_INFO_TYPE)
            # ret, rsp_data = smart_download_package(req_data)
            uri = '/restconf/operations/huawei-software:smart-load-package'
            ret, _, rsp_data = ops_conn.create(uri, req_data)
            if ops_return_result(ret):
                ret = ERR
            else:
                ret = OK

            if ret == ERR:
                print_ztp_log(
                    f'Failed to use smart download file {os.path.basename(local_path)} using SFTP.(reason={rsp_data})',
                    LOG_ERROR_TYPE)
                return ret
            while True:
                # 查询下载结果
                # ret, rsp_data = get_smart_load_package_result()
                uri = '{}'.format(f'/restconf/data/huawei-software:software/smart-load-package-result')
                req_data = None
                ret, _, rsp_data = ops_conn.get(uri, req_data)
                if ops_return_result(ret):
                    ret = ERR
                else:
                    ret = OK
                # print_ztp_log(f'SFTP smart download result {rsp_data}.', LOG_INFO_TYPE)
                if ret == ERR:
                    print_ztp_log(
                        f'Failed to query smart download file {os.path.basename(local_path)} using SFTP.(reason={rsp_data})',
                        LOG_ERROR_TYPE)
                    break
                root_elem = etree.fromstring(rsp_data)
                action_progress = root_elem.find('.//{urn:huawei:yang:huawei-software}action-progress')
                action_status = root_elem.find('.//{urn:huawei:yang:huawei-software}action-status')
                if action_status.text == 'fail':
                    ret = ERR
                    print_ztp_log(
                        f'Failed to query smart download file {os.path.basename(local_path)} using SFTP.(reason={rsp_data})',
                        LOG_ERROR_TYPE)
                    break
                # 下载没有完成
                if action_progress is not None and action_progress.text != '100':
                    sleep(5)
                    continue
                else:
                    # 下载完成，设置软件名称
                    softname = root_elem.find('.//{urn:huawei:yang:huawei-software}name')
                    if softname is not None:
                        ztp_smart_load_name = softname.text
                        ret = OK
                        print_ztp_log(f'Success to smart download file {softname.text} using SFTP.',
                                      LOG_INFO_TYPE)
                        break
            print_ztp_log(f'ret {ret}.', LOG_INFO_TYPE)
            return ret
        else:
            ret, _, _ = ops_conn.create(uri, req_data)
            if ops_return_result(ret):
                logging.error('Failed to download file "%s" using SFTP ret %s' % (os.path.basename(local_path),ret))
                ret = ERR
            else:
                ret = OK
            return ret
    except Exception as reason:
        print_ztp_log(f'Failed to download file {os.path.basename(local_path)} using SFTP. (reason={reason})',
                    LOG_ERROR_TYPE)
        return ERR


@ops_conn_operation
def set_sshc_sha1_status(switch, ops_conn=None):
    if switch not in ["true", "false"]:
        return ERR

    uri = "/restconf/data/huawei-sshc:sshc/pubkey-alg"
    str_temp = string.Template('''
        <pubkey-alg>
            <ecc>$enable</ecc>
            <rsa>$enable</rsa>
        </pubkey-alg>
        ''')
    req_data = str_temp.substitute(enable=switch)
    ret, _, rsp_data = ops_conn.set(uri, req_data)
    if ops_return_result(ret):
        print_ztp_log(f'set ssh sha1 failed switch = {switch}', LOG_ERROR_TYPE)
        return ERR, yang_func_ret_err(ret, rsp_data)
    return OK, yang_func_ret_success


def _sftp_sha1_download_file(url='', local_path=''):
    print_ztp_log(f'SFTP sha1 download {os.path.basename(url)} to {local_path}.', LOG_INFO_TYPE)
    set_sshc_sha1_status('true')
    ret = _sftp_download_file_yang(url=url, local_path=local_path)
    set_sshc_sha1_status('false')
    return ret


@ops_conn_operation
def _sftp_v6_download_file_yang(ops_conn=None, url='', local_path=''):
    print_ztp_log(f'SFTP ipv6 download {os.path.basename(url)} to {local_path}.', LOG_INFO_TYPE)
    uri = '{}'.format('/restconf/operations/huawei-sshc:ssh-transfer-file')
    str_temp = string.Template('''\
<input>
    <server-port>$serverPort</server-port>
    <host-addr-ipv6>$serverIp</host-addr-ipv6>
    <command-type>get</command-type>
    <user-name>$username</user-name>
    <password>$password</password>
    <local-file-name>$localPath</local-file-name>
    <remote-file-name>$remotePath</remote-file-name>
</input>
''')
    url_tuple = urlparse(url)
    if check_addr(url_tuple.hostname) == 'DHCPv6':
        server_ip = url_tuple.hostname
    else:
        server_ip = get_ipv6_addr_by_hostname(host=url_tuple.hostname)
    global sftp_server
    sftp_server = server_ip
    if url_tuple.port == None:
        server_port = SFTP_DEFAULT_PORT
    else:
        server_port = url_tuple.port
    req_data = str_temp.substitute(serverIp=server_ip,
                                   serverPort=server_port,
                                   username=url_tuple.username,
                                   password=url_tuple.password,
                                   remotePath=url_tuple.path[1:],
                                   localPath=local_path)
    req_params = {}.fromkeys(('ip', 'port', 'username', 'password', 'path', 'filename'))
    req_params['ip'] = server_ip
    req_params['port'] = url_tuple.port if url_tuple.port is not None else SFTP_DEFAULT_PORT
    req_params['username'] = url_tuple.username
    req_params['password'] = url_tuple.password
    req_params['path'] = url_tuple.path[1:]
    req_params['filename'] = os.path.basename(url)
    global ztp_smart_load_name
    try:
        if package_pool_flag:
            # 构造入参
            req_data = create_sftp_smart_load_req(req_params, 'ipv6')
            # print_ztp_log(f'SFTP smart download req_data {req_data}.', LOG_INFO_TYPE)
            # ret, rsp_data = smart_download_package(req_data)
            uri = '/restconf/operations/huawei-software:smart-load-package'
            ret, _, rsp_data = ops_conn.create(uri, req_data)
            if ops_return_result(ret):
                ret = ERR
            else:
                ret = OK

            if ret == ERR:
                print_ztp_log(
                    f'Failed to use smart download file {os.path.basename(local_path)} using SFTP.(reason={rsp_data})',
                    LOG_ERROR_TYPE)
                return ret
            while True:
                # 查询下载结果
                # ret, rsp_data = get_smart_load_package_result()
                uri = '{}'.format(f'/restconf/data/huawei-software:software/smart-load-package-result')
                req_data = None
                ret, _, rsp_data = ops_conn.get(uri, req_data)
                if ops_return_result(ret):
                    ret = ERR
                else:
                    ret = OK
                # print_ztp_log(f'SFTP smart download result {rsp_data}.', LOG_INFO_TYPE)
                if ret == ERR:
                    print_ztp_log(
                        f'Failed to query smart download file {os.path.basename(local_path)} using SFTP.(reason={rsp_data})',
                        LOG_ERROR_TYPE)
                    break
                root_elem = etree.fromstring(rsp_data)
                action_progress = root_elem.find('.//{urn:huawei:yang:huawei-software}action-progress')
                action_status = root_elem.find('.//{urn:huawei:yang:huawei-software}action-status')
                if action_status.text == 'fail':
                    ret = ERR
                    print_ztp_log(
                        f'Failed to query smart download file {os.path.basename(local_path)} using SFTP.(reason={rsp_data})',
                        LOG_ERROR_TYPE)
                    break
                # 下载没有完成
                if action_progress is not None and action_progress.text != '100':
                    sleep(5)
                    continue
                else:
                    # 下载完成，设置软件名称
                    softname = root_elem.find('.//{urn:huawei:yang:huawei-software}name')
                    if softname is not None:
                        ztp_smart_load_name = softname.text
                        ret = OK
                        print_ztp_log(f'Success to smart download file {softname.text} using SFTP.',
                                      LOG_INFO_TYPE)
                        break
            return ret
        else:
            ret, _, rsp_data = ops_conn.create(uri, req_data)
            if ops_return_result(ret):
                logging.error('Failed to download file "%s" using SFTP ret %s, reason=%s.'
                    % (os.path.basename(local_path), ret, rsp_data))
                ret = ERR
            else:
                ret = OK
            return ret
    except Exception as reason:
        print_ztp_log(f'Failed to download file {os.path.basename(local_path)} using SFTP. (reason={reason})',
                    LOG_ERROR_TYPE)
        return ERR


def _sftp_sha1_v6_download_file(url='', local_path=''):
    print_ztp_log(f'SFTP sha1 IPV6 download {os.path.basename(url)} to {local_path}.', LOG_INFO_TYPE)
    set_sshc_sha1_status('true')
    ret = _sftp_v6_download_file_yang(url=url, local_path=local_path)
    set_sshc_sha1_status('false')
    return ret


@ops_conn_operation
def _http_download_file(ops_conn=None, url='', local_path=''):
    """Download files using HTTP.

    Args:
        url: URL of a remote file, for example,http://hostname[:port]/path
        local_path: The path must start with the root directory flash:, for example, flash:/vrpcfg.cfg or vrpcfg.cfg.
    """
    print_ztp_log(f'HTTP download {os.path.basename(url)} to {local_path}.', LOG_INFO_TYPE)
    uri = "{}".format('/restconf/operations/huawei-sztp:ztp-http-download')
    req_template = string.Template('''
        <input>
            <fileurl>$file_url</fileurl>
            <filepath>$file_path</filepath>
        </input>
        ''')

    file_dir, _, _ = get_home_path()
    local_path = '{}{}'.format(file_dir, '/')

    url_tuple = urlparse(url)
    if not re.match(r"\d+\.\d+\.\d+\.\d+", url_tuple.hostname):
        ip_address = get_addr_by_hostname(url_tuple.hostname)
        if url_tuple.port is None:
            url = f'{url_tuple.scheme}://{ip_address}:{HTTP_DEFAULT_PORT}{url_tuple.path}'
        else:
            url = f'{url_tuple.scheme}://{ip_address}:{url_tuple.port}{url_tuple.path}'
    req_data = req_template.safe_substitute(file_url=url, file_path=local_path)

    try:
        ret, _, _ = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            logging.error('Failed to download file "%s" using HTTP ret %s' % (os.path.basename(local_path),ret))
            ret = ERR
        else:
            ret = OK
        return ret
    except Exception as reason:
        print_ztp_log(f'Failed to download file {os.path.basename(local_path)} using HTTP. (reason={reason})',
                    LOG_ERROR_TYPE)
        return ERR

def create_ftp_smart_load_req(req_params, type):
    req_str = '{}'.format(f'''
        <input>
            <file-name>$fileName</file-name>
            <ftp-server-ip-version>$type</ftp-server-ip-version>
            <ftp-server>$serverIp</ftp-server>
            <ftp-user-name>$userName</ftp-user-name>
            <ftp-password>$password</ftp-password>
            <ftp-port>$serverPort</ftp-port>
        </input>
        ''')
    req_template = string.Template(req_str)
    req_data = req_template.substitute(serverIp=req_params.get('ip'),
                                        serverPort=req_params.get('port'),
                                        userName=req_params.get('username'),
                                        password=req_params.get('password'),
                                        fileName=req_params.get('filename'),
                                        type=type)
    return req_data

@ops_conn_operation
def _ftp_download_file(ops_conn=None, url='', local_path=''):
    print_ztp_log(f'FTP download {os.path.basename(url)} to {local_path}.', LOG_INFO_TYPE)
    uri = '{}'.format('/restconf/operations/huawei-ftpc:ftpc-transfer-file')
    str_temp = string.Template('''
        <input>
            <server-port>$serverPort</server-port>
            <server-ipv4-address>$serverIp</server-ipv4-address>
            <command-type>get</command-type>
            <user-name>$username</user-name>
            <password>$password</password>
            <local-file-name>$localPath</local-file-name>
            <remote-file-name>$remotePath</remote-file-name>
        </input>
    ''')
    url_tuple = urlparse(url)
    if re.match(r"\d+\.\d+\.\d+\.\d+", url_tuple.hostname):
        server_ip = url_tuple.hostname
    else:
        server_ip = get_addr_by_hostname(host=url_tuple.hostname)
    global sftp_server
    sftp_server = server_ip
    if url_tuple.port == None:
        server_port = FTP_DEFAULT_PORT
    else:
        server_port = url_tuple.port
    req_data = str_temp.substitute(serverIp=server_ip,
                                   serverPort=server_port,
                                   username=url_tuple.username,
                                   password=url_tuple.password,
                                   remotePath=url_tuple.path[1:],
                                   localPath=local_path)
    req_params = {}.fromkeys(('ip', 'username', 'password', 'path', 'filename'))
    req_params['ip'] = server_ip
    req_params['port'] = url_tuple.port if url_tuple.port is not None else DEFAULT_PORT_FTP
    req_params['username'] = url_tuple.username
    req_params['password'] = url_tuple.password
    req_params['path'] = url_tuple.path[1:]
    req_params['filename'] = os.path.basename(url)
    global ztp_smart_load_name
    try:
        if package_pool_flag:
            # 构造入参
            req_data = create_ftp_smart_load_req(req_params, 'ipv4')
            # print_ztp_log(f'FTP smart download req_data {req_data}.', LOG_INFO_TYPE)
            # ret, rsp_data = smart_download_package(req_data)
            uri = '/restconf/operations/huawei-software:smart-load-package'
            ret, _, rsp_data = ops_conn.create(uri, req_data)
            if ops_return_result(ret):
                ret = ERR
            else:
                ret = OK

            if ret == ERR:
                print_ztp_log(
                    f'Failed to use smart download file {os.path.basename(local_path)} using FTP.(reason={rsp_data})',
                    LOG_ERROR_TYPE)
                return ret
            while True:
                # 查询下载结果
                # ret, rsp_data = get_smart_load_package_result()
                uri = '{}'.format(f'/restconf/data/huawei-software:software/smart-load-package-result')
                req_data = None
                ret, _, rsp_data = ops_conn.get(uri, req_data)
                if ops_return_result(ret):
                    ret = ERR
                else:
                    ret = OK
                # print_ztp_log(f'FTP smart download result {rsp_data}.', LOG_INFO_TYPE)
                if ret == ERR:
                    print_ztp_log(
                        f'Failed to query smart download file {os.path.basename(local_path)} using FTP.(reason={rsp_data})',
                        LOG_ERROR_TYPE)
                    break
                root_elem = etree.fromstring(rsp_data)
                action_progress = root_elem.find('.//{urn:huawei:yang:huawei-software}action-progress')
                action_status = root_elem.find('.//{urn:huawei:yang:huawei-software}action-status')
                if action_status.text == 'fail':
                    ret = ERR
                    print_ztp_log(
                        f'Failed to query smart download file {os.path.basename(local_path)} using FTP.(reason={rsp_data})',
                        LOG_ERROR_TYPE)
                    break
                # 下载没有完成
                if action_progress is not None and action_progress.text != '100':
                    sleep(5)
                    continue
                else:
                    # 下载完成，设置软件名称
                    softname = root_elem.find('.//{urn:huawei:yang:huawei-software}name')
                    if softname is not None:
                        ztp_smart_load_name = softname.text
                        ret = OK
                        print_ztp_log(f'Success to smart download file {softname.text} using SFTP.',
                                      LOG_INFO_TYPE)
                        break
            return ret
        else:
            ret, _, _ = ops_conn.create(uri, req_data)
            if ops_return_result(ret):
                logging.error('Failed to download file "%s" using FTP ret %s' % (os.path.basename(local_path),ret))
                ret = ERR
            else:
                ret = OK
            return ret
    except Exception as reason:
        print_ztp_log(f'Failed to download file {os.path.basename(local_path)} using FTP. (reason={reason})',
                    LOG_ERROR_TYPE)
        return ERR


@ops_conn_operation
def _tftp_download_file(ops_conn=None, url='', local_path=''):
    print_ztp_log(f'TFTP download {os.path.basename(url)} to {local_path}.', LOG_INFO_TYPE)
    req_params = {}.fromkeys(('ip', 'username', 'password', 'path'))
    url_tuple = urlparse(url)
    if re.match(r"\d+\.\d+\.\d+\.\d+", url_tuple.hostname):
        req_params['ip'] = url_tuple.hostname
    else:
        req_params['ip'] = get_addr_by_hostname(host=url_tuple.hostname)
    req_params['path'] = url_tuple.path[1:]

    uri = '{}'.format('/restconf/operations/huawei-tftpc:tftpc-transfer-file')
    str_temp = string.Template('''
    <input>
        <server-ipv4-address>$serverIp</server-ipv4-address>
        <local-file-name>$localPath</local-file-name>
        <remote-file-name>$remotePath</remote-file-name>
        <command-type>get</command-type>
    </input>
    ''')
    req_data = str_temp.substitute(serverIp=req_params.get('ip'),
                                       remotePath=req_params.get('path'),
                                       localPath = local_path)

    try:
        ret, _, _ = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            logging.error('Failed to download file "%s" using TFTP ret %s' % (os.path.basename(local_path),ret))
            ret = ERR
        else:
            ret = OK
        return ret
    except Exception as reason:
        print_ztp_log(f'Failed to download file {os.path.basename(local_path)} using TFTP. (reason={reason})',
                    LOG_ERROR_TYPE)
        return ERR

def get_ipv6_address_by_url(url_tuple):
    if check_addr(url_tuple.hostname) == 'DHCPv6':
        return url_tuple.hostname
    else:
        return get_ipv6_addr_by_hostname(host=url_tuple.hostname)

@ops_conn_operation
def _usb_download_file(ops_conn=None, url='', local_path=''):
    """Download file using usb"""
    print_ztp_log(f'USB download {os.path.basename(url)} to {local_path}.', LOG_INFO_TYPE)
    src_path = os.path.join(usb_home_path, os.path.basename(url))
    try:
        copy_file(src_path, local_path)
    except Exception as reason:
        print_ztp_log(f'Failed to download file {os.path.basename(local_path)} using USB. (reason={reason})',
                      LOG_ERROR_TYPE)
        return ERR
    return OK


@ops_conn_operation
def reboot_system(save_config='false', ops_conn=None):
    """ Reboot system """

    uri = '/restconf/operations/huawei-devm:reboot'
    req_template = string.Template('''
        <input>
            <save-flag>$saveConfig</save-flag>
        </input>
        ''')
    req_data = req_template.substitute(saveConfig=save_config)
    ret, _, rsp_data = ops_conn.create(uri, req_data)
    if ops_return_result(ret):
        return ERR, yang_func_ret_err(ret, rsp_data)
    return OK, yang_func_ret_success


@ops_conn_operation
def _tftp_v6_download_file(ops_conn=None, url='', local_path=''):
    logging.info('TFTPv6 download "%s" to "%s".', os.path.basename(url), local_path)
    req_params = {}.fromkeys(('ip', 'path'))
    url_tuple = urlparse(url)
    req_params['ip'] = get_ipv6_address_by_url(url_tuple)

    req_params['path'] = url_tuple.path[1:]

    try:
        uri = '{}'.format('/restconf/operations/huawei-tftpc:tftpc-transfer-file')
        str_temp = string.Template('''
            <input>
                <server-ipv6-address>$serverIp</server-ipv6-address>
                <local-file-name>$localPath</local-file-name>
                <remote-file-name>$remotePath</remote-file-name>
                <command-type>get</command-type>
            </input>
        ''')
        req_data = str_temp.substitute(serverIp=req_params.get('ip'),
                                       remotePath=req_params.get('path'),
                                       localPath=local_path)
        ret, _, rsp_data = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            logging.error('Failed to download file "%s" using TFTP IPv6.'
                          '(ret=%s, reason=%s)' % (os.path.basename(local_path), ret, rsp_data))
            ret = ERR
        else:
            ret = OK
        return ret
    except Exception as reason:
        logging.error('Failed to download file "%s" using TFTP IPv6.'
                      '(reason=%s)' % (os.path.basename(local_path), reason))
        return ERR

@ops_conn_operation
def _ftp_v6_download_file(ops_conn=None, url='', local_path=''):
    logging.info('FTPv6 download "%s" to "%s".', os.path.basename(url), local_path)
    req_params = {}.fromkeys(('ip', 'username', 'password', 'path', 'filename'))
    url_tuple = urlparse(url)
    req_params['ip'] = get_ipv6_address_by_url(url_tuple)

    req_params['port'] = url_tuple.port if url_tuple.port is not None else DEFAULT_PORT_FTP
    req_params['username'] = url_tuple.username
    req_params['password'] = url_tuple.password
    req_params['path'] = url_tuple.path[1:]
    req_params['filename'] = os.path.basename(url)
    global ztp_smart_load_name
    try:
        if package_pool_flag:
            # 构造入参
            req_data = create_ftp_smart_load_req(req_params, 'ipv6')
            # print_ztp_log(f'FTP smart download req_data {req_data}.', LOG_INFO_TYPE)
            # ret, rsp_data = smart_download_package(req_data)
            uri = '/restconf/operations/huawei-software:smart-load-package'
            ret, _, rsp_data = ops_conn.create(uri, req_data)
            if ops_return_result(ret):
                ret = ERR
            else:
                ret = OK

            if ret == ERR:
                print_ztp_log(
                    f'Failed to use smart download file {os.path.basename(local_path)} using SFTP.(reason={rsp_data})',
                    LOG_ERROR_TYPE)
                return ret
            while True:
                # 查询下载结果
                # ret, rsp_data = get_smart_load_package_result()
                uri = '{}'.format(f'/restconf/data/huawei-software:software/smart-load-package-result')
                req_data = None
                ret, _, rsp_data = ops_conn.get(uri, req_data)
                if ops_return_result(ret):
                    ret = ERR
                else:
                    ret = OK
                # print_ztp_log(f'FTP smart download result {rsp_data}.', LOG_INFO_TYPE)
                if ret == ERR:
                    print_ztp_log(
                        f'Failed to query smart download file {os.path.basename(local_path)} using FTP.(reason={rsp_data})',
                        LOG_ERROR_TYPE)
                    break
                root_elem = etree.fromstring(rsp_data)
                action_progress = root_elem.find('.//{urn:huawei:yang:huawei-software}action-progress')
                action_status = root_elem.find('.//{urn:huawei:yang:huawei-software}action-status')
                if action_status.text == 'fail':
                    ret = ERR
                    print_ztp_log(
                        f'Failed to query smart download file {os.path.basename(local_path)} using FTP.(reason={rsp_data})',
                        LOG_ERROR_TYPE)
                    break
                # 下载没有完成
                if action_progress is not None and action_progress.text != '100':
                    sleep(5)
                    continue
                else:
                    # 下载完成，设置软件名称
                    softname = root_elem.find('.//{urn:huawei:yang:huawei-software}name')
                    if softname is not None:
                        ztp_smart_load_name = softname.text
                        ret = OK
                        print_ztp_log(f'Success to smart download file {softname.text} using SFTP.',
                                      LOG_INFO_TYPE)
                        break
            return ret
        else:
            uri = '{}'.format('/restconf/operations/huawei-ftpc:ftpc-transfer-file')
            str_temp = string.Template('''
                <input>
                    <server-port>$serverPort</server-port>
                    <server-ipv6-address>$serverIp</server-ipv6-address>
                    <command-type>get</command-type>
                    <user-name>$username</user-name>
                    <password>$password</password>
                    <local-file-name>$localPath</local-file-name>
                    <remote-file-name>$remotePath</remote-file-name>
                </input>
            ''')
            req_data = str_temp.substitute(serverIp=req_params.get('ip'),
                                       serverPort=req_params.get('port'),
                                       username=req_params.get('username'),
                                       password=req_params.get('password'),
                                       remotePath=req_params.get('path'),
                                       localPath=local_path)
            ret, _, rsp_data = ops_conn.create(uri, req_data)
            if ops_return_result(ret):
                logging.error('Failed to download file "%s" using FTPv6.'
                          '(ret=%s, reason=%s)' % (os.path.basename(local_path), ret, rsp_data))
                ret = ERR
            else:
                ret = OK
            return ret
    except Exception as reason:
        logging.error('Failed to download file "%s" using FTPv6.'
                      '(reason=%s)' % (os.path.basename(local_path), reason))
        return ERR

@ops_conn_operation
def _http_v6_download_file(ops_conn=None, url='', local_path=''):
    file_dir, _, _ = get_home_path()
    local_path = '{}{}'.format(file_dir, '/')
    print_ztp_log(f'HTTP IPv6 download {os.path.basename(url)} to {local_path}.', LOG_INFO_TYPE)

    # URL解析
    url_tuple = urlparse(url)
    username = url_tuple.username
    password = url_tuple.password
    if check_addr(url_tuple.hostname) != 'DHCPv6':
        ipv6_address = get_ipv6_addr_by_hostname(host=url_tuple.hostname)
        if url_tuple.port is None:
            url = f'{url_tuple.scheme}://[{ipv6_address}]:{DEFAULT_PORT_HTTP}{url_tuple.path}'
        else:
            url = f'{url_tuple.scheme}://[{ipv6_address}]:{url_tuple.port}{url_tuple.path}'

    if username is None and password is None:
        uri = "{}".format('/restconf/operations/huawei-sztp:ztp-http-download')
        req_template = string.Template('''
            <input>
                <fileurl>$file_url</fileurl>
                <filepath>$file_path</filepath>
            </input>
            ''')
        req_data = req_template.safe_substitute(file_url=url, file_path=local_path)
    elif username is not None and password is not None:
        uri = "{}".format('/restconf/operations/huawei-http:httpc-transfer-file')
        req_template = string.Template('''
            <input>
                <operation-type>download</operation-type>
                <file-url>$url</file-url>
                <file-full-path>$filePath</file-full-path>
                <user-name>$name</user-name>
                <password>$passwd</password>
                <over-tls>false</over-tls>
            </input>
            ''')
        url = url.replace(f"{username}:{password}@", '')
        req_data = req_template.safe_substitute(url=url, filePath=local_path, name=username, passwd=password)
    else:
        info = "Url must contain both the user name and password or does not contain the user name and password."
        print_ztp_log(info, LOG_ERROR_TYPE)
        return ERR
    try:
        ret, _, rsp_data = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            logging.error('Failed to download file "%s" using HTTP IPv6.'
                          '(ret=%s, reason=%s)' % (os.path.basename(local_path), ret, rsp_data))
            ret = ERR
        else:
            ret = OK
        return ret
    except Exception as reason:
        logging.error('Failed to download file "%s" using HTTP IPv6.'
                      '(reason=%s)' % (os.path.basename(local_path), reason))
        return ERR

def get_trans_protocol_func():
    func_dict = {
        'sftp': _sftp_download_file_yang,
        'tftp': _tftp_download_file,
        'ftp': _ftp_download_file,
        'http': _http_download_file,
	    'sftp-sha1': _sftp_sha1_download_file,
        'file': _usb_download_file,
    }
    return func_dict

def get_v6_trans_protocol_func():
    func_dict = {
        'sftp': _sftp_v6_download_file_yang,
        'tftp': _tftp_v6_download_file,
        'ftp': _ftp_v6_download_file,
        'http': _http_v6_download_file,
	    'sftp-sha1': _sftp_sha1_v6_download_file,
        'file': _usb_download_file,
    }
    return func_dict

def download_file(url, local_path, retry_times=0, is_dhcpv4=True):
    """Download files using SFTP.
    sftp://[username[:password]@]hostname[:port]/path
    Download files using HTTP
    http://hostname[:port]/path
    Args:
      url: URL of remote file
      local_path: local path to put the file

    Returns:
        A integer of return code
    """
    url_tuple = urlparse(url)
    func_dict = {}
    if is_dhcpv4:
        func_dict = get_trans_protocol_func()
    else:
        func_dict = get_v6_trans_protocol_func()
    scheme = url_tuple.scheme
    if scheme not in func_dict.keys():
        raise ZTPErr('Unknown file transfer scheme %s' % scheme)
    display_path = url_tuple.path[1:] if url_tuple.path.startswith('/') else local_path
    print_ztp_log(f"Download {display_path} to {local_path}...", LOG_INFO_TYPE)
    ret = OK
    cnt = 0
    while (cnt < 1 + retry_times):
        if cnt:
            print_ztp_log('Retry downloading...', LOG_INFO_TYPE)
        if cnt == retry_times and scheme == 'sftp':
            scheme = 'sftp-sha1'
        ret = func_dict[scheme](url=url, local_path=local_path)
        if ret is OK:
            break
        cnt += 1

    if ret is not OK:
        logging.warning('Try to delete the file that failed to download')
        clean_download_temp_file(os.path.basename(url))
        raise ZTPErr('Failed to download file "%s"' % os.path.basename(url))

    return OK


def download_v6_file(url, local_path, retry_times=0):
    url_tuple = urlparse(url)
    print_ztp_log(f"Download {url_tuple.path[1:]} to {local_path} through IPv6...", LOG_INFO_TYPE)
    func_dict = {
        'sftp': _sftp_v6_download_file_yang
    }
    scheme = url_tuple.scheme
    if scheme not in func_dict.keys():
        raise ZTPErr('Unknown file transfer scheme %s' % scheme)
    ret = OK
    cnt = 0
    while (cnt < 1 + retry_times):
        if cnt:
            print_ztp_log('Retry downloading...', LOG_INFO_TYPE)
        if cnt == retry_times and scheme == 'sftp':
            scheme = 'sftp-sha1'
        ret = func_dict[scheme](url=url, local_path=local_path)
        if ret is OK:
            break
        cnt += 1

    if ret is not OK:
        logging.warning('Try to delete the file that failed to download')
        clean_download_temp_file(os.path.basename(url))
        raise ZTPErr('Failed to download file "%s"' % os.path.basename(url))

    return OK


@ops_conn_operation
def get_feature_status(featurename = '', ops_conn=None):
    items = ['feature-name', 'status']
    filtering_str = ';'.join(items)
    uri = "{}".format(f'/restconf/data?fields=/huawei-software:software/') + \
        f'startup-features/startup-feature({filtering_str})'
    req_data = None
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ret == http.client.NOT_FOUND:
        rsp_data = '<software xmlns="urn:huawei:yang:huawei-software"></software>'
    else:
        if ops_return_result(ret) or rsp_data == '':
            raise OPIExecError('Failed to get the startup feature current status information')

    root_elem = etree.fromstring(rsp_data)
    node_path = 'software:software/software:startup-features/software:startup-feature'
    namespaces = {'software' : 'urn:huawei:yang:huawei-software'}
    elems = root_elem.findall(node_path, namespaces)
    if elems is None:
        return OK
    features = {}
    cur_feature_files = []
    next_feature_files = []
    nlen = len(namespaces.get('software'))
    for elem in elems:
        key = ''
        value = ''
        for child in elem:
            if child.tag[nlen + 2:] == 'feature-name':
                key = child.text
            elif child.tag[nlen + 2:] == 'status':
                value = child.text
            else:
                pass

        if key != '' and value != '':
            features.update({key:value})

    if features.get(featurename) != 'active':
        return OK
    else:
        return ERR


@ops_conn_operation
def uninstall_weakea_feature(ops_conn=None):
    cnt = 0
    file_delete(file_path=ZTP_INSTALL_FEATURE)
    uri = '/restconf/operations/huawei-software:uninstall-feature-software'
    req_template = string.Template('''
        <input>
            <name>$fileName</name>
        </input>
        ''')
    req_data = req_template.substitute(fileName='WEAKEA')
    while cnt < 3:
        ret, _, rsp_data = ops_conn.create(uri, req_data)
        result = check_weakea_schedule(operation_type='uninstall-feature-software')
        if not ops_return_result(ret) and result == OK:
            return
        logging.warning(f'uninstall weakea feature failed, try cnt {cnt}...')
        cnt = cnt + 1
        sleep(15)
    logging.error('Have tried to uninstall weakea feature failed for 3 times')


@ops_conn_operation
def check_scheme_install_weakea(url = '', install_weak = None, ops_conn=None):
    url_tuple = urlparse(url)
    scheme = url_tuple.scheme
    uri = '/restconf/operations/huawei-software:install-feature-software'
    req_template = string.Template('''
        <input>
            <name>$fileName</name>
        </input>
        ''')
    req_data = req_template.substitute(fileName="WEAKEA")
    if scheme in ['tftp', 'ftp'] or install_weak is not None:
        ret = get_feature_status("WEAKEA")
        if ret == OK:
            ret, _, rsp_data = ops_conn.create(uri, req_data)
            result = check_weakea_schedule(operation_type='install-feature-software')
            if ops_return_result(ret) or result != OK:
                raise ZTPErr('Failed to install weakea feature.')
            record_mark_file(ZTP_INSTALL_FEATURE)
            return OK

    return None


@ops_conn_operation
def get_software_progress(operation_item, ops_conn=None):
    schedule_dict = {}
    uri = f'/restconf/data?fields=/huawei-software:software/operation-schedules(operation-schedule)'
    req_data = None
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ops_return_result(ret) or rsp_data == '':
        print_ztp_log('Failed to get the next software operation schedule.', LOG_WARN_TYPE)
        return schedule_dict

    namespaces = {'software': 'urn:huawei:yang:huawei-software'}
    node_path = "software:software/software:operation-schedules/software:operation-schedule"
    root_elem = etree.fromstring(rsp_data)
    elems = root_elem.findall(node_path, namespaces)
    if elems is None:
        return schedule_dict

    for elem in elems:
        phase_node = elem.find('software:operation-type', namespaces)
        if phase_node is not None and phase_node.text == operation_item:
            status_node = elem.find('software:status', namespaces)
            if status_node is not None:
                schedule_dict['status'] = status_node.text
    return schedule_dict


def check_weakea_schedule(operation_type, retry_times=30):
    ret = ERR
    cnt = 0
    while cnt < retry_times:
        sleep(10)
        schedule_dict = get_software_progress(operation_type)
        status = schedule_dict.get('status')
        if status == "successful":
            return OK
        elif status == "failed":
            return ERR
        else:
            cnt += 1

    return ret


class StartupInfo(object):
    """ Startup configuration information

    image:          startup system software
    config:         startup saved-configuration file
    patch:          startup patch package
    feature_image:  startup feature software
    mod_list:       startup module list
    """

    def __init__(self, image=None, config=None, patch=None, mod_list=None, feature_plugin_list=None):
        # display startup
        self.image = image
        self.config = config
        self.patch = patch
        self.feature_plugin_list = feature_plugin_list
        # display module-information [next-startup]
        self.mod_list = mod_list


    def __eq__(self, obj):
        if not isinstance(obj, StartupInfo):
            return False

        if self.image != obj.image or self.config != obj.config or self.patch != obj.patch:
            return False

        if self.feature_plugin_list is not None:
            self.feature_plugin_list.sort()

        if obj.feature_plugin_list is not None:
            obj.feature_plugin_list.sort()

        if self.feature_plugin_list != obj.feature_plugin_list:
            return False

        if self.mod_list is not None:
            self.mod_list.sort()

        if obj.mod_list is not None:
            obj.mod_list.sort()

        if self.mod_list != obj.mod_list:
            return False

        return True

class Startup(object):
    """Startup configuration information

    current: current startup configuration
    next:    current next startup configuration
    """
    def __init__(self):
        self.current, self.next = self.get_startup_info()
        self.is_need_clear_config = False
        self.exportcfg = None

    def set_exportcfg(self, export_value):
        logging.info('Import configuration file.')
        if export_value is not None:
            self.exportcfg = export_value

    def print_startup_info(self):
        def get_info_str(info):
            return str(info)

        print_info = "Startup information of the current device:\n"
        print_info += "{: <26}{: <68}{: <68}\n".format('item-name', 'configured', 'next-startup')
        print_info += "-" * 150
        print_info += "\n"
        print_info += "{: <26}{: <68}{: <68}\n".format('system software',
            get_info_str(self.current.image), get_info_str(self.next.image))
        print_info += "{: <26}{: <68}{: <68}\n".format('saved-configurated file',
            get_info_str(self.current.config), get_info_str(self.next.config))
        print_info += "{: <26}{: <68}{: <68}\n".format('patch package',
            get_info_str(self.current.patch), get_info_str(self.next.patch))

        current_mod_info_len = len(self.current.mod_list)
        next_mod_info_len = len(self.next.mod_list)
        mod_info_len = max(current_mod_info_len, next_mod_info_len)
        if mod_info_len == 0:
            print_info += "{: <26}{: <68}{: <68}\n".format("module information", "None", "None")
        else:
            current_mod_info_print = [self.current.mod_list[i] if i < current_mod_info_len else "" for i in range(mod_info_len)]
            next_mod_info_print = [self.next.mod_list[i] if i < next_mod_info_len else "" for i in range(mod_info_len)]
            flag = True
            for i in range(mod_info_len):
                _item_name = "module information"
                if not flag:
                    _item_name = ""
                print_info += "{: <26}{: <68}{: <68}\n".format(_item_name, current_mod_info_print[i], next_mod_info_print[i])
                flag = False

        current_feature_plugin_info_len = len(self.current.feature_plugin_list)
        next_feature_plugin_info_len = len(self.next.feature_plugin_list)
        feature_plugin_info_len = max(current_feature_plugin_info_len, next_feature_plugin_info_len)
        if feature_plugin_info_len == 0:
            print_info += "{: <26}{: <68}{: <68}\n".format("feature software", "None", "None")
        else:
            current_feature_plugin_info_print = [self.current.feature_plugin_list[i] if i < current_feature_plugin_info_len else "" for i in range(feature_plugin_info_len)]
            next_feature_plugin_info_print = [self.next.feature_plugin_list[i] if i < next_feature_plugin_info_len else "" for i in range(feature_plugin_info_len)]
            flag = True
            for i in range(feature_plugin_info_len):
                _item_name = "feature software"
                if not flag:
                    _item_name = ""
                print_info += "{: <26}{: <68}{: <68}\n".format(_item_name, current_feature_plugin_info_print[i], next_feature_plugin_info_print[i])
                flag = False

        logging.info(print_info)

    @staticmethod
    def get_startup_info_by_type(file_type):
        def func_execption_retry_policy(sleep_interval, try_times, func, *argv):
            for _ in range(try_times):
                try:
                    return func(*argv)
                except OPIExecError as reason:
                    logging.warning(f"{reason}, retry...")
                    sleep(sleep_interval)
            raise OPIExecError(f"Failed to get startup {file_type} information for many times.")

        func_dict = {
            FILE_TYPE_CFG:              Startup.get_cfg_info,
            FILE_TYPE_PAT:              Startup.get_patch_info,
            FILE_TYPE_SOFTWARE:         Startup.get_software_info,
            FILE_TYPE_MOD:              Startup.get_mod_patch_info,
            FILE_TYPE_FEATURE_PLUGIN:   Startup.get_feature_plugin_info
        }
        func = func_dict.get(file_type)
        if func is None:
            return None, None
        return func_execption_retry_policy(GET_STARTUP_INTERVAL, MAX_TIMES_GET_STARTUP, func)

    @staticmethod
    @ops_conn_operation
    def get_cfg_info(ops_conn=None):
        items = ['current-cfg-file', 'next-cfg-file']
        filtering_str = ';'.join(items)
        uri = "{}".format(f'/restconf/data?fields=/huawei-cfg:cfg/startup-infos/startup-info({filtering_str})')
        req_data = None
        ret, _, rsp_data = ops_conn.get(uri, req_data)
        if ops_return_result(ret) or rsp_data == '':
            raise OPIExecError('Failed to get the current config file information')

        node_dict = {}
        root_elem = etree.fromstring(rsp_data)
        namespaces = {'cfg': 'urn:huawei:yang:huawei-cfg'}
        elems = root_elem.find('cfg:cfg/cfg:startup-infos/cfg:startup-info', namespaces)
        if elems is None:
            return None, None

        nslen = len(namespaces.get('cfg'))
        for elem in elems:
            tag_name = elem.tag[nslen + 2:]
            if elem.text is None or elem.text == 'NULL':
                continue
            node_dict[tag_name] = elem.text

        current_cfg = node_dict.get('current-cfg-file')
        if current_cfg is not None:
            current_cfg = os.path.basename(current_cfg)

        next_cfg = node_dict.get('next-cfg-file')
        if next_cfg is not None:
            next_cfg = os.path.basename(next_cfg)

        return current_cfg, next_cfg

    @staticmethod
    @ops_conn_operation
    def get_software_info(ops_conn=None):
        items = ['current-package', 'next-package']
        filtering_str = ';'.join(items)
        uri = "{}".format(f'/restconf/data?fields=/huawei-software:software/startup-packages/startup-package({filtering_str})')
        req_data = None
        ret, _, rsp_data = ops_conn.get(uri, req_data)
        if ret == http.client.NOT_FOUND:
            rsp_data = '<software xmlns="urn:huawei:yang:huawei-software"></software>'
        else:
            if ops_return_result(ret) or rsp_data == '':
                raise OPIExecError('Failed to get the startup software information')

        root_elem = etree.fromstring(rsp_data)
        namespaces = {'software': 'urn:huawei:yang:huawei-software'}
        elems = root_elem.find('software:software/software:startup-packages/software:startup-package', namespaces)
        if elems is None:
            return None, None

        node_dict = {}
        nslen = len(namespaces.get('software'))
        for elem in elems:
            tag_name = elem.tag[nslen + 2:]
            if elem.text is None or elem.text == 'NULL':
                continue
            node_dict[tag_name] = elem.text

        cur_image = node_dict.get('current-package')
        if cur_image is not None:
            cur_image = os.path.basename(cur_image)

        next_image = node_dict.get('next-package')
        if next_image is not None:
            next_image = os.path.basename(next_image)

        return cur_image, next_image

    @staticmethod
    @ops_conn_operation
    def get_patch_info(ops_conn=None):
        items = ['patch-infos', 'next-startup-patchs']
        filtering_str = ';'.join(items)
        uri = "{}".format(f'/restconf/data?fields=/huawei-patch:patch({filtering_str})')
        req_data = None
        ret, _, rsp_data = ops_conn.get(uri, req_data)
        if ret == http.client.NOT_FOUND:
            return None, None

        if ops_return_result(ret) or rsp_data == '':
            raise OPIExecError('Failed to get the patch file information')

        root_elem = etree.fromstring(rsp_data)
        namespaces = {'patch': 'urn:huawei:yang:huawei-patch'}
        elems = root_elem.find('patch:patch/patch:patch-infos/patch:patch-info', namespaces)
        node_dict = {}
        cur_pat_file = None
        if elems is not None:
            nslen = len(namespaces.get('patch'))
            for elem in elems:
                tag_name = elem.tag[nslen + 2:]
                node_dict[tag_name] = elem.text

            cur_pat_file = node_dict.get("name")
            if cur_pat_file is not None:
                cur_pat_file = os.path.basename(cur_pat_file)

        elems = root_elem.find('patch:patch/patch:next-startup-patchs/patch:next-startup-patch', namespaces)
        if elems is None:
            return cur_pat_file, None

        node_dict = {}
        nslen = len(namespaces.get('patch'))
        for elem in elems:
            tag_name = elem.tag[nslen + 2:]
            node_dict[tag_name] = elem.text

        next_pat_file = node_dict.get("name")
        if next_pat_file is not None:
            next_pat_file = os.path.basename(next_pat_file)

        return cur_pat_file, next_pat_file

    @staticmethod
    @ops_conn_operation
    def get_mod_patch_info(ops_conn=None):
        items = ['module-infos', 'next-startup-modules']
        filtering_str = ';'.join(items)
        uri = "{}".format(f'/restconf/data?fields=/huawei-module-management:module-management({filtering_str})')
        req_data = None
        ret, _, rsp_data = ops_conn.get(uri, req_data)
        if ret == http.client.NOT_FOUND:
            return [] ,[]

        if ops_return_result(ret) or rsp_data == '':
            raise OPIExecError('Failed to get the mod patch file information')

        root_elem = etree.fromstring(rsp_data)
        namespaces = {'module-management' : 'urn:huawei:yang:huawei-module-management'}
        cur_mod_patch_files = []
        node_path = 'module-management:module-management/module-management:module-infos/module-management:module-info'
        elems = root_elem.findall(node_path, namespaces)
        if elems is not None:
            for elem in elems:
                elem_text = elem.find('module-management:package-name', namespaces)
                cur_mod_patch_files.append(elem_text.text)

        next_mod_patch_files = []
        node_path = 'module-management:module-management/module-management:next-startup-modules/module-management:next-startup-module'
        elems = root_elem.findall(node_path, namespaces)
        if elems is not None:
            for elem in elems:
                elem_text = elem.find('module-management:name', namespaces)
                next_mod_patch_files.append(elem_text.text)

        return cur_mod_patch_files, next_mod_patch_files


    @staticmethod
    @ops_conn_operation
    def get_feature_plugin_info(ops_conn=None):
        items = ['current-feature-packages', 'next-feature-packages']
        filtering_str = ';'.join(items)
        uri = "{}".format(f'/restconf/data?fields=/huawei-software:software/startup-packages/startup-package({filtering_str})')
        req_data = None
        ret, _, rsp_data = ops_conn.get(uri, req_data)
        if ret == http.client.NOT_FOUND:
            rsp_data = '<software xmlns="urn:huawei:yang:huawei-software"></software>'
        else:
            if ops_return_result(ret) or rsp_data == '':
                raise OPIExecError('Failed to get the startup software information')

        root_elem = etree.fromstring(rsp_data)
        node_path = 'software:software/software:startup-packages/software:startup-package'
        namespaces = {'software' : 'urn:huawei:yang:huawei-software'}
        elems = root_elem.findall(node_path, namespaces)
        if elems is None:
            return [], []

        cur_feature_files = []
        next_feature_files = []
        nlen = len(namespaces['software'])
        for elem in elems:
            for child in elem:
                if child.tag[nlen + 2:] == 'current-feature-packages':
                    feature_plugin = os.path.basename(child.text)
                    cur_feature_files.append(feature_plugin)
                elif child.tag[nlen + 2:] == 'next-feature-packages':
                    feature_plugin = os.path.basename(child.text)
                    next_feature_files.append(feature_plugin)
                else:
                    pass
            break
        return cur_feature_files, next_feature_files

    def get_startup_info(self):
        """Get the startup information."""
        print_ztp_log("Start to get the startup information...", LOG_INFO_TYPE)
        current = StartupInfo()
        curnext = StartupInfo()

        current.config, curnext.config =               Startup.get_startup_info_by_type(FILE_TYPE_CFG)
        current.patch, curnext.patch =                 Startup.get_startup_info_by_type(FILE_TYPE_PAT)
        current.image, curnext.image =                 Startup.get_startup_info_by_type(FILE_TYPE_SOFTWARE)
        current.feature_plugin_list, curnext.feature_plugin_list = Startup.get_startup_info_by_type(FILE_TYPE_FEATURE_PLUGIN)
        current.mod_list, curnext.mod_list =           Startup.get_startup_info_by_type(FILE_TYPE_MOD)

        return current, curnext

    @staticmethod
    @ops_conn_operation
    def set_mod_patch_file(file_path, ops_conn=None):
        uri = '/restconf/operations/huawei-module-management:install-module'
        req_template = string.Template('''
            <input>
                <name>$fileName</name>
            </input>
            ''')
        req_data = req_template.substitute(fileName=file_path)
        ret, _, rsp_data = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            logging.error(f'set_mod_patch_file failed. (reason={rsp_data})')
            raise OPIExecError('Failed to set the mod patch file')

    def clean_next_config_file(self):
        if self.is_need_clear_config == False:
            return

        _, nextcfg = self.get_startup_info_by_type(FILE_TYPE_CFG)
        if nextcfg is not None:
            self._del_startup_config_file()
            sleep(5)

    @ops_conn_operation
    def set_next_mod_patch_file(self, file_path, ops_conn=None):
        uri = '/restconf/operations/huawei-module-management:startup-module'
        req_template = string.Template('''
            <input>
                <name>$fileName</name>
            </input>
            ''')
        req_data = req_template.substitute(fileName=file_path)
        ret, _, rsp_data = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            logging.error(f'set_next_mod_patch_file failed. (reason={rsp_data})')
            raise OPIExecError('Failed to set the next mod patch file')

    @ops_conn_operation
    def startup_next_feature_software(self, file_path, ops_conn=None):
        """ Set next feature software file """
        uri = '/restconf/operations/huawei-software:startup-feature-software'
        req_template = string.Template('''
            <input>
                <feature-package-name>$fileName</feature-package-name>
            </input>
            ''')
        req_data = req_template.substitute(fileName=file_path)
        ret, _, rsp_data = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            raise OPIExecError(f"Failed to set next feature plugin {rsp_data}.")

    @ops_conn_operation
    def unset_mod_patch_file(self, file_path, ops_conn=None):
        uri = '/restconf/operations/huawei-module-management:uninstall-module'
        req_template = string.Template('''
            <input>
                <action-type>single</action-type>
                <name>$fileName</name>
            </input>
            ''')
        req_data = req_template.substitute(fileName=file_path)
        ret, _, rsp_data = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            logging.error(f'unset_mod_patch_file failed. (reason={rsp_data})')
            raise OPIExecError('Failed to unset the mod patch file')

    @staticmethod
    @ops_conn_operation
    def set_feature_software(file_path, ops_conn=None):
        uri = '/restconf/operations/huawei-software:install-feature-software'
        req_template = string.Template('''
            <input>
                <name>$fileName</name>
            </input>
            ''')
        req_data = req_template.substitute(fileName=file_path)
        ret, _, rsp_data = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            logging.error(f'Failed to set the feature software file. (reason={rsp_data})')
            raise OPIExecError('Failed to set the feature software file')

    @ops_conn_operation
    def uninstall_feature_software(self, file_path, ops_conn=None):
        """ Install feature software file """
        uri = '/restconf/operations/huawei-software:uninstall-feature-software'
        req_template = string.Template('''
            <input>
                <name>$fileName</name>
            </input>
            ''')
        req_data = req_template.substitute(fileName=file_path)
        ret, _, _ = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            return ERR
        return OK

    def unset_feature_file_list(self, file_list, slave):
        for file in file_list:
            logging.info("Unset the feature plugin file...")
            ret = self.uninstall_feature_software(file)
            if ret == ERR:
                logging.error(f"Failed unset feature {file}.")
                continue
            ret = check_weakea_schedule(operation_type='uninstall-feature-software')
            if ret == ERR:
                print_ztp_log(f"Check unset feature {file} schedule failed.", LOG_ERROR_TYPE)
                continue
            file_delete_on_MPUs(file, slave)

    def reset_next_feature_file_list(self, file_list, slave):
        for file in file_list:
            logging.info("Reset the next feature plugin file...")
            ret, _ = cli.reset_next_feature_plugin(file)
            if ret == ERR:
                logging.error(f"Failed reset next feature {file}.")
                continue
            file_delete_on_MPUs(file, slave)


    @ops_conn_operation
    def _set_startup_image_file(self, file_path, ops_conn=None):
        """Set the next startup system software."""
        logging.info("Set the next startup system software "
                     "to {}...".format(file_path))

        uri = '/restconf/operations/huawei-software:startup-by-mode'
        str_temp = string.Template('''\
<input>
    <name>$fileName</name>
    <mode>all</mode>
</input>
''')
        req_data = str_temp.substitute(fileName=file_path)
        ret, _, _ = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            slog.syslog("Set the next startup system software to {} failed."\
                .format(file_path), ops.ERROR, ops.SYSLOG)
            raise OPIExecError("Failed to set startup system software.")

        slog.syslog("Set the next startup system software to {} successfully."\
            .format(file_path), ops.INFORMATIONAL, ops.SYSLOG)

    @ops_conn_operation
    def _set_startup_config_file(self, file_path, exportcfg=None, ops_conn=None):
        """Set the configuration file for the next startup."""
        logging.info("Set the next startup saved-configuration file "
                     "to {}...".format(file_path))

        uri = '/restconf/operations/huawei-cfg:set-startup'
        req_data = ''
        if exportcfg is not None:
            exportcfg_change = ops.opscharacterEncode(exportcfg)
            items = {'filename': file_path, 'shareable-mode': 'password', 'password': exportcfg_change}
        else:
            items = {'filename': file_path, 'shareable-mode': 'default'}

        for key in items.keys():
            req_data = '{}{}'.format(req_data, item_str(key, items[key]))

        req_data = item_str('input', req_data)
        ret, _, data = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            logging.error(f"Set the next startup saved-configuration file to {data} failed")
            slog.syslog("Set the next startup saved-configuration file to {} failed."\
                .format(file_path), ops.ERROR, ops.SYSLOG)
            raise OPIExecError("Failed to set startup configuration file.")

        slog.syslog("Set the next startup saved-configuration file to {} successfully."\
            .format(file_path), ops.INFORMATIONAL, ops.SYSLOG)

    @ops_conn_operation
    def _del_startup_config_file(self, ops_conn=None):
        """Clear the startup configuration file."""
        logging.info("Delete the next startup config file...")

        uri = '/restconf/operations/huawei-cfg:clear-startup'
        req_data = '''
<input>
</input>
'''
        ret, _, _ = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            raise OPIExecError("Failed to clear startup configuration file.")

    @ops_conn_operation
    def _set_startup_patch_file(self, file_path, ops_conn=None):
        """Set the next startup patch file."""
        logging.info("Set the next startup patch file "
                     "to {}...".format(file_path))

        uri = '/restconf/operations/huawei-patch:startup-next-patch'
        str_temp = string.Template('''\
<input>
    <name>$fileName</name>
</input>
''')
        req_data = str_temp.substitute(fileName=file_path)
        ret, _, _ = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            slog.syslog("Set the next startup patch file to {} failed."\
                .format(file_path), ops.ERROR, ops.SYSLOG)
            raise OPIExecError("Failed to set startup patch file.")

        slog.syslog("Set the next startup patch file to {} successfully."\
            .format(file_path), ops.INFORMATIONAL, ops.SYSLOG)

    def set_next_mod_patch_file_list(self, mod_patch_file, slave):
        if mod_patch_file is None:
            return

        try:
            self.set_next_mod_patch_file(mod_patch_file)
            ret = self._check_set_startup_schedule(set_type=SET_MOD_PATCH, phase_item="startup-module", retry_times=MAX_TIMES_GET_STARTUP)
            if ret == ERR:
                raise Exception("Set startup info {} failed".format(SET_MOD_PATCH))

            if self.is_need_clear_config:
                _, nextcfg = self.get_startup_info_by_type(FILE_TYPE_CFG)
                if nextcfg is not None:
                    self._del_startup_config_file()
                    sleep(5)
        except Exception as reason:
            logging.error(reason)
            self.reset_startup_info(slave)
            file_delete(f'flash:/{mod_patch_file}')
            file_delete(f'flash:/$_install_mod/{mod_patch_file}')
            raise

    def set_next_feature_plugin(self, file_name, slave):
        if file_name is None:
            return

        try:
            logging.info("Set the next feature plugin file...")
            self.startup_next_feature_software(file_name)

            ret = self._check_set_startup_info(SET_FEATURE_PLUGIN, file_name, TIMES_STARTUP_RETRY)
            if ret != OK:
                raise Exception("Set startup info {} failed".format(SET_FEATURE_PLUGIN))

            self.clean_next_config_file()
        except Exception as reason:
            logging.error(reason)
            self.reset_startup_info(slave)
            raise

    def reset_mod_patch_file_list(self, cur_mod_list, pre_next_mod_list, slave):
        del_mod_file_list = []
        for mod_file in cur_mod_list:
            if mod_file not in pre_next_mod_list:
                del_mod_file_list.append(mod_file)

        for mod_patch_file in del_mod_file_list:
            src_file_path = f'flash:/{mod_patch_file}'
            dest_file_path = f'flash:/$_install_mod/{mod_patch_file}'
            try:
                self.unset_mod_patch_file(mod_patch_file)
                ret = self._check_set_startup_schedule(set_type=SET_MOD_PATCH, phase_item="uninstall-module", retry_times=MAX_TIMES_GET_STARTUP)
                if ret == ERR:
                    raise Exception("Unset startup info {} failed".format(SET_MOD_PATCH))

                file_delete(src_file_path)
                file_delete(dest_file_path)
            except Exception as reason:
                logging.error(reason)

        if self.is_need_clear_config:
            _, nextcfg = self.get_startup_info_by_type(FILE_TYPE_CFG)
            if nextcfg is not None:
                self._del_startup_config_file()
                sleep(5)

    def reset_feature_plugin_file(self, pre_cur_file_list, configured_cur_file_list, pre_next_file_list, configured_next_file_list, slave):
        unset_file_list = [file for file in configured_cur_file_list if file not in pre_cur_file_list]
        self.unset_feature_file_list(unset_file_list, slave)

        reset_file_list = [file for file in configured_next_file_list if file not in pre_next_file_list and file not in configured_cur_file_list]
        self.reset_next_feature_file_list(reset_file_list, slave)

        self.clean_next_config_file()

    def reset_old_feature_plugin_file(self, pre_next_file_list, configured_next_file_list, slave):
        for file_name in pre_next_file_list:
            if file_name in configured_next_file_list:
                continue
            try:
                self.set_next_feature_plugin(file_name, slave)
            except Exception as reason:
                print_ztp_log(reason, LOG_ERROR_TYPE)
        self.clean_next_config_file()

    def rollback_feature_plugin_file(self, cur_file_list, pre_file_list):
        for file in cur_file_list:
            if pre_file_list is not None and file in pre_file_list:
                continue

            logging.info(f"Reset the feature software file {file}...")
            ret, rsp_data = cli.reset_next_feature_plugin(file)
            if ret == ERR:
                logging.error(f'Failed to reset the feature software file {rsp_data}')
            sleep(5)

        self.clean_next_config_file()

    def rollback_mod_patch_file_list(self, cur_mod_list, pre_next_mod_list):
        del_mod_file_list = []
        for mod_file in cur_mod_list:
            if pre_next_mod_list is not None and mod_file in pre_next_mod_list:
                continue
            del_mod_file_list.append(mod_file)

        for mod_patch_file in del_mod_file_list:
            try:
                self.unset_mod_patch_file(mod_patch_file)
                ret = self._check_set_startup_schedule(set_type=SET_MOD_PATCH, phase_item="uninstall-module", retry_times=MAX_TIMES_GET_STARTUP)
                if ret == ERR:
                    logging.warning("Unset startup info {} failed".format(SET_MOD_PATCH))
            except Exception as reason:
                logging.error(reason)

        if self.is_need_clear_config:
            _, nextcfg = self.get_startup_info_by_type(FILE_TYPE_CFG)
            if nextcfg is not None:
                self._del_startup_config_file()
                sleep(5)

    @ops_conn_operation
    def _reset_startup_patch_file(self, ops_conn=None):
        """Reset the patch file for system startup."""
        logging.info("Reset the next startup patch file...")

        uri = '/restconf/operations/huawei-patch:reset-startup-patch'
        req_data = '''\
<input>
    <delete-type>all</delete-type>
</input>
'''
        ret, _, _ = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            raise OPIExecError('Failed to reset patch.')

    def reset_startup_info(self, slave):
        """Reset startup info and delete the downloaded files"""
        print_ztp_log("Reset the next startup information...", LOG_INFO_TYPE)
        cur_startup_info, configured = self.get_startup_info()

        self.is_need_clear_config = True
        if self.next.config is not None:
            self.is_need_clear_config = False

        try:
            if configured.config != self.next.config:
                if self.next.config is None:
                    self._del_startup_config_file()
                    sleep(15)
                else:
                    self._set_startup_config_file(self.next.config)
                    ret = self._check_set_startup_info(set_type=SET_CFG, file_path=self.next.config, retry_times=TIMES_STARTUP_RETRY)
                    if ret == ERR:
                        logging.warning("Set startup info {} failed".format(SET_CFG))

                if configured.config is not None:
                    file_delete_on_MPUs(configured.config, slave)

        except Exception as reason:
            logging.error(reason)

        self.reset_feature_plugin_file(self.current.feature_plugin_list, cur_startup_info.feature_plugin_list,
                                       self.next.feature_plugin_list, configured.feature_plugin_list, slave)

        try:
            if configured.image != self.next.image:
                self._set_startup_image_file(self.next.image)
                ret = self._check_set_startup_info(set_type=SET_SOFTWARE, file_path=self.next.image, retry_times=TIMES_STARTUP_RETRY)
                if ret == ERR:
                    logging.warning("Set startup info {} failed".format(SET_SOFTWARE))

                if self.is_need_clear_config:
                    _, nextcfg = self.get_startup_info_by_type(FILE_TYPE_CFG)
                    if nextcfg is not None:
                        self._del_startup_config_file()
                        sleep(5)
                sleep(90)
                file_delete_on_MPUs(configured.image, slave)
        except Exception as reason:
            logging.error(reason)
        
        try:
            if cur_startup_info.patch != self.current.patch:
                if self.current.patch is None:
                    cli.patch_delete_all()
                else:
                    self.patch_active_proc(self.current.patch)
                    if self.is_need_clear_config:
                        _, nextcfg = self.get_startup_info_by_type(FILE_TYPE_CFG)
                        if nextcfg is not None:
                            self._del_startup_config_file()
                            sleep(5)
                if cur_startup_info.patch is not None:
                    file_delete_on_MPUs(cur_startup_info.patch, slave)

            if configured.patch != self.next.patch:
                if self.next.patch is None:
                    self._reset_startup_patch_file()
                    ret = self._check_set_startup_schedule(set_type=SET_PATCH, phase_item="reset-startup-patch", retry_times=MAX_TIMES_GET_STARTUP)
                    if ret == ERR:
                        logging.warning("Reset startup info {} failed".format(SET_PATCH))
                else:
                    self._set_startup_patch_file(self.next.patch)
                    ret = self._check_set_startup_schedule(set_type=SET_PATCH, phase_item="startup-next-patch", retry_times=MAX_TIMES_GET_STARTUP)
                    if ret == ERR:
                        logging.warning("Set startup info {} failed".format(SET_PATCH))

                if self.is_need_clear_config:
                    _, nextcfg = self.get_startup_info_by_type(FILE_TYPE_CFG)
                    if nextcfg is not None:
                        self._del_startup_config_file()
                        sleep(5)
                if configured.patch is not None:
                    file_delete_on_MPUs(configured.patch, slave)

        except Exception as reason:
            logging.error(reason)

        self.reset_old_feature_plugin_file(self.next.feature_plugin_list, configured.feature_plugin_list, slave)

        self.reset_mod_patch_file_list(configured.mod_list, self.next.mod_list, slave)

    @staticmethod
    @ops_conn_operation
    def get_software_image_info(images_name, ops_conn=None):
        images_name = images_name.replace('/', '%2F')
        uri = "{}".format(f'/restconf/data/huawei-software:software/packages/package={images_name}')
        ret, _, rsp_data = ops_conn.get(uri, None)
        if ops_return_result(ret) or rsp_data == '':
            return ERR, yang_func_ret_err(ret, rsp_data)
        return OK, rsp_data

    def get_software_version(self, image_file):
        image_file = "flash:/" + image_file
        ret, rsp_data = self.get_software_image_info(image_file)
        if ret == ERR:
            print_ztp_log(f"Failed to get {image_file} version, {rsp_data}", LOG_WARN_TYPE)
            return ""
        root = etree.fromstring(rsp_data)
        version = root.find('{urn:huawei:yang:huawei-software}version')
        if version is None:
            print_ztp_log(f"Failed to get {image_file} version", LOG_WARN_TYPE)
            return ""
        return version.text

    def set_next_image_with_fail(self, image_file):
        if self.next.feature_plugin_list is None:
            return ERR
        next_version = self.get_software_version(image_file)
        curr_version = self.get_software_version(self.next.image)
        if next_version == "" or curr_version == "" or next_version == curr_version:
            return ERR
        for file in self.next.feature_plugin_list:
            print_ztp_log("Reset the next feature plugin file...", LOG_INFO_TYPE)
            ret, _ = cli.reset_next_feature_plugin(file)
            if ret == ERR:
                print_ztp_log(f"Failed reset next feature {file}.", LOG_ERROR_TYPE)
                continue
        return self.set_next_image(image_file)

    def set_next_image(self, image_file):
        try:
            self._set_startup_image_file(image_file)
            ret = self._check_set_startup_info(set_type=SET_SOFTWARE, file_path=image_file, retry_times=TIMES_STARTUP_RETRY)
            if ret == ERR:
                return ERR
        except Exception as reason:
            return ERR
        return OK

    def set_startup_info(self, image_file=None, config_file=None, patch_file=None,
                         mod_file=None, feature_plugin=None, slave=0):
        """Set the next startup information."""
        print_ztp_log("Set the next startup information...", LOG_INFO_TYPE)
        self.is_need_clear_config = True
        if self.next.config is not None:
            self.is_need_clear_config = False

        # 1. Set next startup system software
        if image_file is not None:
            try:
                ret = self.set_next_image(image_file)
                if ret == ERR and self.set_next_image_with_fail(image_file) == ERR:
                    raise Exception("Set startup info {} failed".format(SET_SOFTWARE))

                if self.is_need_clear_config:
                    _, nextcfg = self.get_startup_info_by_type(FILE_TYPE_CFG)
                    if nextcfg is not None:
                        self._del_startup_config_file()
                        sleep(5)
            except Exception as reason:
                logging.error(reason)
                file_delete_on_MPUs(image_file, slave)
                self.reset_startup_info(slave)
                raise

        # 2. Set next startup patch file
        if patch_file is not None:
            try:
                self._set_startup_patch_file(patch_file)
                ret = self._check_set_startup_schedule(set_type=SET_PATCH, phase_item="startup-next-patch", retry_times=MAX_TIMES_GET_STARTUP)
                if ret == ERR:
                    raise Exception("Set startup info {} failed".format(SET_PATCH))

                if self.is_need_clear_config:
                    _, nextcfg = self.get_startup_info_by_type(FILE_TYPE_CFG)
                    if nextcfg is not None:
                        self._del_startup_config_file()
                        sleep(5)
            except Exception as reason:
                logging.error(reason)
                file_delete_on_MPUs(patch_file, slave)
                self.reset_startup_info(slave)
                raise

        # 3. Set mod patch
        self.set_next_mod_patch_file_list(mod_file, slave)
        self.set_next_feature_plugin(feature_plugin, slave)

        # 4. Set next startup config file
        if config_file is not None:
            try:
                self._set_startup_config_file(config_file, self.exportcfg)
                ret = self._check_set_startup_info(set_type=SET_CFG, file_path=config_file, retry_times=TIMES_STARTUP_RETRY)
                if ret == ERR:
                    raise Exception("Set startup info {} failed".format(SET_CFG))
            except Exception as reason:
                logging.error(reason)
                file_delete_on_MPUs(config_file, slave)
                self.reset_startup_info(slave)
                raise

    def rollback_startup_info(self, image_file, config_file=None, patch_file=None,
                              mod_file_list=None, feature_plugin_list=None):
        """Rollback startup information."""

        print_ztp_log("Rollback startup information...", LOG_INFO_TYPE)
        _, configured = self.get_startup_info()

        self.is_need_clear_config = True
        if config_file is not None:
            self.is_need_clear_config = False
        # 1. Reset next startup config file
        try:
            if configured.config != config_file:
                if config_file is None:
                    self._del_startup_config_file()
                    sleep(15)
                else:
                    self._set_startup_config_file(config_file)
                    ret = self._check_set_startup_info(set_type=SET_CFG, file_path=config_file, retry_times=TIMES_STARTUP_RETRY)
                    if ret == ERR:
                        logging.warning("Set startup info {} failed".format(SET_CFG))
        except Exception as reason:
            logging.error(reason)

        # 2. Reset next startup patch file
        try:
            if configured.patch != patch_file:
                if patch_file is None:
                    self._reset_startup_patch_file()
                    ret = self._check_set_startup_schedule(set_type=SET_PATCH, phase_item="reset-startup-patch", retry_times=MAX_TIMES_GET_STARTUP)
                    if ret == ERR:
                        logging.warning("Reset startup info {} failed".format(SET_PATCH))
                else:
                    self._set_startup_patch_file(patch_file)
                    ret = self._check_set_startup_schedule(set_type=SET_PATCH, phase_item="startup-next-patch", retry_times=MAX_TIMES_GET_STARTUP)
                    if ret == ERR:
                        logging.warning("Set startup info {} failed".format(SET_PATCH))

                if self.is_need_clear_config:
                    _, nextcfg = self.get_startup_info_by_type(FILE_TYPE_CFG)
                    if nextcfg is not None:
                        self._del_startup_config_file()
                        sleep(5)
        except Exception as reason:
            logging.error(reason)

        # 3. Reset the next startup system software
        try:
            if configured.image != image_file:
                self._set_startup_image_file(image_file)
                ret = self._check_set_startup_info(set_type=SET_SOFTWARE, file_path=image_file, retry_times=TIMES_STARTUP_RETRY)
                if ret == ERR:
                    logging.warning("Set startup info {} failed".format(SET_SOFTWARE))
                sleep(90)

                if self.is_need_clear_config:
                    _, nextcfg = self.get_startup_info_by_type(FILE_TYPE_CFG)
                    if nextcfg is not None:
                        self._del_startup_config_file()
                        sleep(5)
        except Exception as reason:
            logging.error(reason)

        # 4. Reset next startup system mod patch
        self.rollback_mod_patch_file_list(configured.mod_list, mod_file_list)
        self.rollback_feature_plugin_file(configured.feature_plugin_list, feature_plugin_list)

    @ops_conn_operation
    def _get_set_next_software_status(self, file_path, ops_conn=None):
        """Get the next software information."""

        print_ztp_log("Get the next startup software information...", LOG_INFO_TYPE)
        items = ['next-package']
        filtering_str = ';'.join(items)
        uri = "{}".format(f'/restconf/data?fields=/huawei-software:software/startup-packages/startup-package({filtering_str})')
        req_data = None
        ret, _, rsp_data = ops_conn.get(uri, req_data)
        if ops_return_result(ret) or rsp_data == '':
            logging.warning('Failed to get the startup information')
            return ERR

        root_elem = etree.fromstring(rsp_data)
        namespaces = {'software': 'urn:huawei:yang:huawei-software'}
        elems = root_elem.find('software:software/software:startup-packages/software:startup-package', namespaces)
        if elems is None:
            return ERR

        node_dict = {}
        nslen = len(namespaces.get('software'))
        for elem in elems:
            tag_name = elem.tag[nslen + 2:]
            if elem.text is None and elem.text == 'NULL':
                continue
            node_dict[tag_name] = elem.text

        next_image = node_dict.get('next-package')
        if next_image is not None:
            next_image = os.path.basename(next_image)

        file_name = os.path.basename(file_path)
        return OK if file_name == next_image else ERR

    @ops_conn_operation
    def _get_set_next_cfg_status(self, file_path, ops_conn=None):
        """Get the next cfg file information."""
        print_ztp_log("Get the next cfg file information...", LOG_INFO_TYPE)
        file_name = os.path.basename(file_path)
        uri = '/restconf/data?fields=/huawei-cfg:cfg/startup-infos/startup-info(next-cfg-file)'
        req_data = None

        ret, _, rsp_data = ops_conn.get(uri, req_data)
        if ops_return_result(ret) or rsp_data == '':
            logging.warning('Failed to get the next cfg file information')
            return ERR

        root_elem = etree.fromstring(rsp_data)
        namespaces = {'data':'urn:ietf:params:xml:ns:yang:ietf-restconf','cfg': 'urn:huawei:yang:huawei-cfg'}
        uriTmp = '{}'.format('/cfg/startup-infos/startup-info')
        uriTmp = uriTmp.replace('/', '/cfg:')
        mpath = uriTmp[1:]
        for info in root_elem.findall(mpath, namespaces):
            elem_name = info.find("cfg:next-cfg-file", namespaces)
            if elem_name is None:
                return ERR
            cfg_file_name = os.path.basename(elem_name.text)
            if cfg_file_name != file_name:
                return ERR

        return OK

    def _get_set_next_feature_image_status(self, file_path):
        _, next_feature_image = Startup.get_feature_plugin_info()
        return ERR if file_path not in next_feature_image else OK

    def _check_set_startup_info(self, set_type, file_path, retry_times=10):
        print_ztp_log(f"Now checking {set_type} is complete or not...", LOG_INFO_TYPE)
        func_dict = {
            SET_SOFTWARE:       self._get_set_next_software_status,
            SET_CFG:            self._get_set_next_cfg_status,
            SET_FEATURE_PLUGIN: self._get_set_next_feature_image_status
        }

        if set_type not in func_dict.keys():
            logging.warning('Unknown check startup type')
            return ERR
        ret = OK
        cnt = 0
        while cnt < retry_times:
            ret = func_dict[set_type](file_path=file_path)
            if ret == ERR:
                cnt += 1
                logging.info("Now system is {}, please wait...".format(set_type))
                sleep(DELAY_INTERVAL_SET_INFO)     # sleep to wait for system ready
                continue
            else:
                sleep(10)   # 查询下次启动项为预期值后，再等待一段时间
                break
        return ret

    @ops_conn_operation
    def _get_patch_progress(self, phase_item, ops_conn=None):
        """Get the next patch file information."""
        uri = f'/restconf/data?fields=/huawei-patch:patch/operation-schedules(operation-schedule)'
        req_data = None
        ret, _, rsp_data = ops_conn.get(uri, req_data)
        schedule_dict = {}
        if ops_return_result(ret) or rsp_data == '':
            logging.warning('Failed to get the next patch operation schedule')
            return schedule_dict

        namespaces = {'patch': 'urn:huawei:yang:huawei-patch'}
        node_path = "patch:patch/patch:operation-schedules/patch:operation-schedule"
        root_elem = etree.fromstring(rsp_data)
        elems = root_elem.findall(node_path, namespaces)
        if elems is None:
            return schedule_dict

        for elem in elems:
            phase_node = elem.find('patch:phase', namespaces)
            if phase_node is not None and phase_node.text == phase_item:
                status_node = elem.find('patch:status', namespaces)
                if status_node is not None:
                    schedule_dict['status'] = status_node.text
                schedule_node = elem.find('patch:schedule', namespaces)
                if schedule_node is not None:
                    schedule_dict['schedule'] = schedule_node.text
                break
        return schedule_dict


    @ops_conn_operation
    def _get_mod_patch_progress(self, phase_item, ops_conn=None):
        """Get the next patch file information."""
        uri = f'/restconf/data?fields=/huawei-module-management:module-management/operation-schedules(operation-schedule)'
        req_data = None
        ret, _, rsp_data = ops_conn.get(uri, req_data)
        schedule_dict = {}
        if ops_return_result(ret) or rsp_data == '':
            logging.warning('Failed to get the next mod patch operation schedule')
            return schedule_dict

        namespaces = {'module-management': 'urn:huawei:yang:huawei-module-management'}
        node_path = "module-management:module-management/module-management:operation-schedules/module-management:operation-schedule"
        root_elem = etree.fromstring(rsp_data)
        elems = root_elem.findall(node_path, namespaces)
        if elems is None:
            return schedule_dict

        for elem in elems:
            phase_node = elem.find('module-management:phase', namespaces)
            if phase_node is not None and phase_node.text == phase_item:
                status_node = elem.find('module-management:status', namespaces)
                if status_node is not None:
                    schedule_dict['status'] = status_node.text
                schedule_node = elem.find('module-management:schedule', namespaces)
                if schedule_node is not None:
                    schedule_dict['schedule'] = schedule_node.text
                break
        return schedule_dict

    def _check_set_startup_schedule(self, set_type, phase_item, retry_times=10):

        print_ztp_log(f"Now checking {set_type} is complete or not...", LOG_INFO_TYPE)
        func_dict = {
            SET_PATCH:    self._get_patch_progress,
            SET_MOD_PATCH: self._get_mod_patch_progress
        }

        if set_type not in func_dict.keys():
            logging.warning('Unknown check startup type')
            return ERR

        ret = ERR
        cnt = 0
        while cnt < retry_times:
            schedule_dict = func_dict[set_type](phase_item=phase_item)
            status = schedule_dict.get('status')
            schedule = schedule_dict.get('schedule')
            print_ztp_log(f"Now schedule is {schedule}, status is {status}...", LOG_INFO_TYPE)
            if schedule == "100" and status == "successful":
                ret = OK
                break
            elif schedule == "100" and status == "failed":
                break
            else:
                cnt += 1
                sleep(10)
        sleep(10)
        return ret

    @ops_conn_operation
    def patch_active_proc(self, patch_name='', ops_conn=None):
        """patch active"""
        if patch_name is None:
            return OK

        curpat, _ = self.get_startup_info_by_type(FILE_TYPE_PAT)
        if curpat is not None:
            cli.patch_delete_all()

        uri = '/restconf/operations/huawei-patch:load-patch'
        req_template = string.Template('''
            <input>
                <name>$patchName</name>
                <load-type>run</load-type>
            </input>
            ''')
        req_data = req_template.substitute(patchName=patch_name)
        ret, _, _ = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            raise OPIExecError('Failed to execute the patch active operation.')

        ret = self._check_set_startup_schedule(set_type=SET_PATCH, phase_item="load-patch", retry_times=MAX_TIMES_GET_STARTUP)
        return ret

    @ops_conn_operation
    def mod_patch_active_proc(self, module_name='', ops_conn=None):
        """MOD active"""
        if module_name is None:
            return OK

        uri = '/restconf/operations/huawei-module-management:install-module'
        req_template = string.Template('''
            <input>
                <name>$fileName</name>
            </input>
            ''')
        req_data = req_template.substitute(fileName=module_name)
        ret, _, _ = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            raise OPIExecError('Failed to execute the mod active operation.')

        ret = self._check_set_startup_schedule(set_type=SET_MOD_PATCH, phase_item="install-module", retry_times=MAX_TIMES_GET_STARTUP)
        return ret

    @ops_conn_operation
    def feature_plugin_active_proc(self, feature_name='', ops_conn=None):
        """feature plugin active"""
        if feature_name is None:
            return OK

        uri = '/restconf/operations/huawei-software:install-feature-software'
        req_template = string.Template('''
            <input>
                <name>$fileName</name>
            </input>
            ''')
        req_data = req_template.substitute(fileName=feature_name)
        ret, _, _ = ops_conn.create(uri, req_data)
        if ops_return_result(ret):
            raise OPIExecError('Failed to execute the feature plugin active operation.')
        ret = self._check_set_startup_info(SET_FEATURE_PLUGIN, feature_name, TIMES_STARTUP_RETRY)
        return ret

    @ops_conn_operation
    def get_active_license_file(self, items, ops_conn=None):
        filtering_str = ';'.join(items)
        uri = "{}".format(f'/restconf/data?fields=/huawei-license:license/license-files/license-file({filtering_str})')
        ret, _, rsp_data = ops_conn.get(uri, None)
        if ops_return_result(ret) or rsp_data == '':
            return ERR, yang_func_ret_err(ret, rsp_data)
        return OK, rsp_data

    @ops_conn_operation
    def license_active_proc(self, license_name='', ops_conn=None):
        """license active"""
        if license_name is None:
            return OK

        uri = '/restconf/operations/huawei-license:license-active'
        req_template = string.Template('''
            <input>
                <filename>$licenseName</filename>
            </input>
            ''')
        req_data = req_template.substitute(licenseName=license_name)
        ret, _, _ = ops_conn.create(uri, req_data)
        if ret == OK:
            print_ztp_log("The license file is successfully activated.", LOG_INFO_TYPE)
        else:
            ret, rsp_date = self.get_active_license_file(['filename'])
            if ret != OK or license_name not in rsp_date:
                raise OPIExecError('Failed to execute the license active operation.')
            print_ztp_log(f"The license file {license_name} is successfully activated.", LOG_INFO_TYPE)
        return ret

    def file_effective_proc(self, file_info_list, file_name_dict, slave):
        """Effect file"""
        print_ztp_log("Activation will be performed.", LOG_INFO_TYPE)
        active_startup_func_dict = {
            FILE_TYPE_PAT :             self.patch_active_proc,
            FILE_TYPE_MOD :             self.mod_patch_active_proc,
            FILE_TYPE_LIC :             self.license_active_proc,
            FILE_TYPE_FEATURE_PLUGIN :  self.feature_plugin_active_proc,
        }

        for file_info in file_info_list:
            effective_mode = file_info.get('*EFFECTIVE_MODE')
            if effective_mode != EFFECTIVE_MODE_NO_REBOOT:
                continue

            file_type = file_info.get('*TYPE').lower()
            func = active_startup_func_dict.get(file_type)
            if func is None:
                continue

            logging.info(f"{file_type.upper()} active...")
            ret = func(file_name_dict.get(file_type))
            if ret == ERR:
                self.reset_startup_info(slave)
                raise ZTPErr(f"Active {file_type} file failed")

    def cfg_effective_proc(self, file_info_list, cfg_name, slave):
        for file_info in file_info_list:
            if file_info.get('*TYPE').lower() != FILE_TYPE_CFG or file_info.get('*EFFECTIVE_MODE') != EFFECTIVE_MODE_NO_REBOOT:
                continue
            ret = cfg_deliver_proc(cfg_name)
            if ret == ERR:
                self.reset_startup_info(slave)
                raise ZTPErr(f"Active file {cfg_name} failed")

def check_filename_length(filename, filetype):
    """File name length check

    Input parameters: filename, filetype
    Return value: OK/ERR
    Function usage: Check whether the name of the downloaded file exceeds the maximum length allowed by the system.
                    If so, an error is returned and the file is not downloaded.
    """
    file_name = os.path.basename(filename)
    if filetype == FILE_TYPE_SOFTWARE:
        if len((file_name)) > FELMNAMME_120 or len(file_name) < FELMNAMME_4:
            logging.error('%s too long or too short, please check!',file_name)
            return ERR
        return OK
    elif filetype == FILE_TYPE_CFG:
        if len((file_name)) > FELMNAMME_64 or len(file_name) < FELMNAMME_5:
            logging.error('%s too long, please check!', file_name)
            return ERR
        return OK
    elif filetype == FILE_TYPE_PACKAGE_POOL:
        if len((file_name)) > FELMNAMME_64 or len(file_name) < FELMNAMME_5:
            logging.error('%s too long or too short, please check!', file_name)
            return ERR
        return OK
    elif filetype == FILE_TYPE_PAT:
        if len((file_name)) > (FELMNAMME_64 - 1) or len(file_name) < FELMNAMME_5:
            logging.error('%s too long or too short, please check!', file_name)
            return ERR
        return OK
    elif filetype == FILE_TYPE_MOD:
        if len((file_name)) > (FELMNAMME_64 - 1) or len(file_name) < FELMNAMME_5:
            logging.error('%s too long or too short, please check!', file_name)
            return ERR
        return OK
    elif filetype == FILE_TYPE_FEATURE_PLUGIN:
        if len((file_name)) > FELMNAMME_120 or len(file_name) < FELMNAMME_4:
            logging.error('%s too long or too short, please check!', file_name)
            return ERR
        return OK
    elif filetype == FILE_TYPE_LIC:
        if len((file_name)) > FELMNAMME_120 or len(file_name) < FELMNAMME_5:
            logging.error('%s too long or too short, please check!', file_name)
            return ERR
        return OK
    else:
        if len((file_name)) > FELMNAMME_64 or len(file_name) < 3:
            logging.error('%s too long or too short, please check!', file_name)
            return ERR
    return OK


@ops_conn_operation
def get_disk_free_size(path='', ops_conn=None):
    """return list of disk free size, types = 0: main, types = 1: slave"""
    uri = '{}'.format('/restconf/data/huawei-file-operation:file-operation/disk-usages')
    disk_info = 0
    req_data = None
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ops_return_result(ret) or rsp_data == '':
        logging.error('Failed to get disk free size')
        return disk_info

    root_elem = etree.fromstring(rsp_data)
    namespaces = {'file-operation': 'urn:huawei:yang:huawei-file-operation'}
    for disk_usage in root_elem.findall("file-operation:disk-usage", namespaces):
        elem = disk_usage.find("file-operation:path", namespaces) # 文件系统分区所在的路径
        if elem is None or elem.text is None:
            continue

        if not elem.text.lower().startswith(path):
            continue

        elem = disk_usage.find("file-operation:free-size", namespaces)
        if elem is not None:
            disk_info = int(elem.text.encode('utf-8').decode('utf-8'))
            return disk_info

    return disk_info


@ops_conn_operation
def del_recycle_bin(ops_conn=None):
    """Delete files from the recycle bin."""
    uri = '{}'.format('/restconf/operations/huawei-file-operation:reset-recycle-bin')
    req_data = '''\
<input>
    <reset-type>all</reset-type>
</input>
'''
    ret, _, _ = ops_conn.create(uri, req_data)
    if ops_return_result(ret):
        logging.error('Delete recycle bin failed.')
        return ERR
    return OK


def space_enough(masterspace, slavespace, filespace, slave):
    if int(filespace) < int(masterspace):
        if slave:
            if int(filespace) < int(slavespace):
                return OK
            else:
                return ERR
        return OK
    else:
        return ERR


def get_space_mode_str(space_clear):
    check_print = 'undefined'
    if space_clear in ['0', None]:
        check_print = 'no cleanup'
    elif space_clear == '1':
        check_print = 'normal cleanup'
    elif space_clear == '2':
        check_print = 'deep cleanup'
    return check_print


def check_devices_space(devices_res_space, need_space):
    for key in devices_res_space.keys():
        if need_space > devices_res_space.get(key):
            return ERR
    return OK

def check_if_space_enough(master_path, cc_image, all_devices_paths, softwareflag):
    current_image_size = get_file_size(file_path=(os.path.join(master_path, cc_image)))
    # Required space
    ztp_min_need_space = current_image_size
    if not softwareflag:
        ztp_min_need_space = 0
    # Obtain the available space of the master and slave MPUs.
    devices_res_space = get_residual_space(all_devices_paths)
    ret = check_devices_space(devices_res_space, ztp_min_need_space + ZTP_CLAER_ADD_SPACE)
    return ret, ztp_min_need_space


def get_residual_space(all_devices_paths=[]):
    """Obtain the available space of the master and slave MPUs."""
    devices_space = {}
    if len(all_devices_paths) == 0:
        return devices_space
    for path in all_devices_paths:
        path_space = get_disk_free_size(path)
        devices_space.update({path : path_space})

    return devices_space


def get_mpus_files_list(all_devices_paths):

    print_ztp_log("Get all file list.", LOG_INFO_TYPE)
    devices_files = {}
    for path in all_devices_paths:
        device_path_list = get_file_list(path)
        devices_files.update({path : device_path_list})

    return devices_files


def get_devices_images_files(files_list, cc_image):
    """Obtain the system software packages on the master and slave MPUs."""

    print_ztp_log("Obtain the list of system software packages.", LOG_INFO_TYPE)
    images_files_list = {}
    files_removes_device_images = {}
    for key in files_list.keys():
        files_removes_images = []
        images_in_devices = []
        for filename in files_list.get(key):
            if os.path.splitext(filename)[-1] in ['.cc', '.CC'] and filename != os.path.basename(cc_image):
                images_in_devices.append(filename)
            if filename != os.path.basename(cc_image):
                files_removes_images.append(filename)
        images_files_list.update({key:images_in_devices})
        files_removes_device_images.update({key:files_removes_images})

    return files_removes_device_images, images_files_list


def get_space_of_files_list(files_list):

    all_files_space = {}
    space_temp = 0
    for key in files_list.keys():
        for filename in files_list.get(key):
            space_temp = space_temp + get_file_size(os.path.join(key, filename))
        all_files_space.update({key:space_temp})
        space_temp = 0
    return all_files_space


def clean_cc_tmp_file(files_list):
    pattern = r".*\.cc.tmp$"
    for key in files_list.keys():
        for filename in files_list.get(key):
            if re.match(pattern, filename.lower()) is not None:
                file_delete(os.path.join(key, filename))

def check_space(startup_info, cc_image, softwareflag):
    master_path, slave_paths, _ = get_home_path()
    all_devices_paths = slave_paths
    all_devices_paths.append(master_path)
    space_clear_strategy = startup_info['SPACE_CLEAR']
    devices_files_list = get_mpus_files_list(all_devices_paths)
    clean_cc_tmp_file(devices_files_list)
    ret, ztp_min_need_space = check_if_space_enough(master_path, cc_image, all_devices_paths, softwareflag)
    need_space = ztp_min_need_space + ZTP_CLAER_ADD_SPACE
    if ret == OK:
        print_ztp_log("The space enough, continue ztp...", LOG_INFO_TYPE)
        return OK

    if space_clear_strategy not in [ZTP_SPACE_CLEAR_NO_NEED, ZTP_SPACE_CLEAR_NORMAL, ZTP_SPACE_CLEAR_DEEP]:
        print_ztp_log("Invalid space clear strategy.", LOG_WARN_TYPE)
        return ERR

    print_ztp_log(f"The space clear strategy is {get_space_mode_str(space_clear_strategy)}.", LOG_INFO_TYPE)
    if space_clear_strategy == ZTP_SPACE_CLEAR_NO_NEED:
        devices_res_space = get_residual_space(all_devices_paths)
        ret = check_devices_space(devices_res_space, ztp_min_need_space)
        if ret == OK:
            print_ztp_log("Current space of the device is insufficient, the deployment may fail. "
                          "You are advised to configure SPACE_CLEAR.", LOG_WARN_TYPE)
            return OK
        print_ztp_log("The current space is insufficient and no clearing policy is "
                      "configured to exit the ZTP process.", LOG_ERROR_TYPE)
        return ERR

    # Clear the recycle bin.
    del_recycle_bin()

    devices_res_space = get_residual_space(all_devices_paths)
    ret = check_devices_space(devices_res_space, need_space)
    if ret == OK:
        print_ztp_log("Empty recycle bin, the space enough and continue ztp...", LOG_INFO_TYPE)
        return OK

    files_removes_device_images, devices_images_list = get_devices_images_files(devices_files_list, cc_image)
    all_files_list_space = get_space_of_files_list(files_removes_device_images)
    all_images_list_space = get_space_of_files_list(devices_images_list)
    space_not_enough_path = []
    space_enough_del = []

    for image_path in all_images_list_space.keys():
        if all_images_list_space.get(image_path) + devices_res_space.get(image_path) < ztp_min_need_space:
            space_not_enough_path.append(image_path)
        else:
            space_enough_del.append(image_path)

    need_del_all_file = {}
    need_del_images_file = {}
    if len(space_not_enough_path) == 0:
        del_list_file(devices_images_list, LOG_FILE)
        print_ztp_log("Delete the system software packages on the master, continue the ZTP process.", LOG_INFO_TYPE)
        ret, _ = check_if_space_enough(master_path, cc_image, all_devices_paths, softwareflag)
        if ret == ERR:
            for path in space_enough_del:
                need_del_all_file.update({path: files_removes_device_images.get(path)})
            del_list_file(need_del_all_file, LOG_FILE)
    elif len(space_not_enough_path) != 0 and space_clear_strategy == ZTP_SPACE_CLEAR_NORMAL:
        print_ztp_log(f"The space of the following {space_not_enough_path} devices is insufficient.", LOG_ERROR_TYPE)
        return ERR
    else:
        for path in space_not_enough_path:
            if all_files_list_space.get(path) + devices_res_space.get(path) < ztp_min_need_space:
                print_ztp_log(f"The space of the following {path} devices is insufficient.", LOG_ERROR_TYPE)
                return ERR
            need_del_all_file.update({path: files_removes_device_images.get(path)})

        for path in space_enough_del:
            need_del_images_file.update({path: devices_images_list.get(path)})

        del_list_file(need_del_all_file, LOG_FILE)
        del_list_file(need_del_images_file, LOG_FILE)
        print_ztp_log("Delete files on master and standby, continue the ZTP process.", LOG_INFO_TYPE)

    # 考虑有存在删除失败的情况，做删除之后应该再次检查空间。尝试清理后，按最低要求检查空间是否足够
    devices_res_space = get_residual_space(all_devices_paths)
    ret = check_devices_space(devices_res_space, ztp_min_need_space)
    if ret == ERR:
        logging.error('Try to clean file failed, the space is still not enough.')
    return ret


def check_file_sha256(path, file_sha256):
    """SHA256 verification on files"""
    if file_sha256 is None or package_pool_flag:
        return OK

    # Calculate the SHA256 value of the file.
    ret, calc_sha256 = sha256_calc(path, False)
    if ret != OK or calc_sha256 != file_sha256:
        return ERR
    return OK


def download_xml(lic_list_file_path, lic_list_file_sha256, startup_info):
    """Download the XML file to be parsed for license-based batch deployment."""
    lic_list_file_name = os.path.basename(lic_list_file_path)
    if lic_list_file_name is not None:
        url = os.path.join(startup_info['*FILESERVER'], lic_list_file_path)
        local_path_file = lic_list_file_name
        logging.info('Download "{}" for get license.'.format(lic_list_file_name))
        file_delete(file_path=local_path_file)
        ret = check_filename_length(url, FILE_TYPE_LIC)
        if ret != OK:
            raise ZTPErr("The file length is incorrect.")

        ret = download_file(url, local_path_file, MAX_TIMES_RETRY_DOWNLOAD, DHCP_TYPE == 'DHCPv4')
        if ret is ERR or not file_exist(file_path=os.path.basename(url)):
            logging.error('Failed to download file "{}"'.format(lic_list_file_name))
            file_delete(file_path=local_path_file)
            return ERR
        logging.info('Download file "{}" successfully.'.format(lic_list_file_name))
        # Add the downloaded file to the list of downloaded files.
        ZTP_DOWNLOAD_FILE_LIST.append(lic_list_file_name)
        # SHA256 verification
        ret = check_file_sha256(local_path_file, lic_list_file_sha256)
        if ret != OK:
            logging.error('{} sha256 check error'.format(lic_list_file_name))
            return ERR

        return OK


def ztp_get_file_list(startup, sys_info, startup_info):
    """Obtain the list of files to be downloaded."""
    file_list = []
    file_name_dict = {}.fromkeys((FILE_TYPE_SOFTWARE, FILE_TYPE_CFG, FILE_TYPE_PAT, FILE_TYPE_MOD, FILE_TYPE_LIC,
                                  FILE_TYPE_FEATURE_PLUGIN, FILE_TYPE_SCRIPT))
    for file_info in startup_info.get('FILE_INFO'):
        file_name = file_info.get('*FILENAME')
        file_type = file_info.get('*TYPE')
        if file_name is not None:
            _file_name = file_name
            _file_path = file_info.get('PATH')
            _file_sha256 = file_info.get('SHA256')
            _file_type = file_type.lower()
            if file_type == FILE_TYPE_SOFTWARE:
                if _file_name in [startup.current.image, startup.next.image]:
                    print_ztp_log('The name of image file to be downloaded is the same as the image file of system.', LOG_WARN_TYPE)
                    continue
                file_name_dict[FILE_TYPE_SOFTWARE] = _file_name
            elif file_type == FILE_TYPE_CFG:
                if _file_name in [startup.current.config, startup.next.config]:
                    print_ztp_log('The name of config file to be downloaded is the same as the config file of system.', LOG_WARN_TYPE)
                    continue
                file_name_dict[FILE_TYPE_CFG] = _file_name
            elif file_type == FILE_TYPE_PAT:
                if _file_name in [startup.current.patch, startup.next.patch]:
                    print_ztp_log('The name of patch file to be downloaded is the same as the patch file of system.', LOG_WARN_TYPE)
                    continue
                file_name_dict[FILE_TYPE_PAT] = _file_name
            elif file_type == FILE_TYPE_MOD:
                if _file_name in startup.current.mod_list or _file_name in startup.next.mod_list:
                    print_ztp_log('The name of mod file to be downloaded is the same as the mod file of system.', LOG_WARN_TYPE)
                    continue
                file_name_dict[FILE_TYPE_MOD] = _file_name
            elif file_type == FILE_TYPE_FEATURE_PLUGIN:
                if _file_name in startup.current.feature_plugin_list or _file_name in startup.next.feature_plugin_list:
                    print_ztp_log('The name of feature_plugin file to be downloaded is the same as the feature_plugin file of system.', LOG_WARN_TYPE)
                    continue
                file_name_dict[FILE_TYPE_FEATURE_PLUGIN] = _file_name
            elif file_type == FILE_TYPE_SCRIPT:
                file_name_dict[FILE_TYPE_SCRIPT] = _file_name
            elif file_type == FILE_TYPE_LIC:
                if file_info.get('ISBATCHPROCESS') != '1':
                    file_name_dict[FILE_TYPE_LIC] = _file_name
                else:
                    # Batch process licenses.
                    ret = download_xml(_file_path, _file_sha256, startup_info)
                    if ret is not OK:
                        raise ZTPErr('Download license list file error.')

                    _license_name, _license_sha256 = get_license_from_xml(sys_info['esn'], _file_name)
                    if _license_name is None:
                        raise ZTPErr('Failed to get license file from license list file.')

                    _file_name_real = os.path.basename(_license_name)
                    _license_name_stripped = _license_name.lstrip('/')
                    if LIC_DOWNLOAD_USE_XML_PATH:
                        _file_path = _license_name_stripped
                    else:
                        _liclist_dir = os.path.dirname(_file_path)
                        _file_path = os.path.join(_liclist_dir, _license_name_stripped)
                    _file_sha256 = _license_sha256

                    logging.info('Get license from {} succesfully.(name={}, sha256={})'\
                        .format(_file_name, _file_name_real, _license_sha256))

                    file_name_dict[FILE_TYPE_LIC] = _file_name_real
            else:
                pass

            file_list.append((_file_path, _file_sha256, _file_type))

    return file_list, file_name_dict


def ztp_file_download(filelist, startup_info, slave):
    """Download all files in the file list."""
    if startup_info.get('DIRECTORY') is None:
        direct = ''
    else:
        direct =  startup_info.get('DIRECTORY')

    chg_flag = False

    print_ztp_log(f"Ztp download filelist: {filelist}.", LOG_INFO_TYPE)
    for _file in filelist:
        if _file[0] is not None:
            _file_path = _file[0]
            _file_name = os.path.basename(_file_path)
            _file_sha256 = _file[1]
            _file_type = _file[2]
            global package_pool_flag
            if _file_type == FILE_TYPE_PACKAGE_POOL:
                package_pool_flag = True
            else:
                package_pool_flag = False
            url = os.path.join(startup_info['*FILESERVER'], direct, _file_path)
            local_path_file = _file_name
            logging.info('The system begins to download {} file.'.format(_file_name))
            slog.syslog('The system begins to download {} file.'.format(_file_name), ops.INFORMATIONAL, ops.SYSLOG)
            file_delete(file_path=local_path_file)
            ret = check_filename_length(url, _file_type)
            if ret != OK:
                raise ZTPErr("The file length is incorrect.")

            ret = download_file(url, local_path_file, MAX_TIMES_RETRY_DOWNLOAD, DHCP_TYPE == 'DHCPv4')
            if ret is ERR or (not file_exist(file_path=os.path.basename(url)) and _file_type != FILE_TYPE_PACKAGE_POOL):
                logging.error('Failed to download file "{}"'.format(_file_name))
                slog.syslog('Failed to download file "{}"'.format(_file_name), ops.ERROR, ops.SYSLOG)
                return ERR, chg_flag
            logging.info('Download file "{}" successfully.'.format(_file_name))
            slog.syslog('Download file "{}" successfully.'.format(_file_name), ops.INFORMATIONAL, ops.SYSLOG)
            # Add the downloaded file to the list of downloaded files.
            if _file_type == FILE_TYPE_PACKAGE_POOL:
                _file_name = ztp_smart_load_name
            ZTP_DOWNLOAD_FILE_LIST.append(_file_name)
            # SHA256 check
            ret = check_file_sha256(local_path_file, _file_sha256)
            if ret != OK:
                slog.syslog('{} sha256 check error'.format(_file_name), ops.ERROR, ops.SYSLOG)
                logging.error('{} sha256 check error'.format(_file_name))
                return ERR, chg_flag
            chg_flag = True
            if slave:
                if (flash_home_path_slave is None or len(flash_home_path_slave) <= 0):
                    return ERR, chg_flag
                print_ztp_log(f"The {_file_name} is being copied to the other master board, please wait...", LOG_INFO_TYPE)
                for path in flash_home_path_slave:
                    file_path_slave = os.path.join(path, _file_name)
                    _ = file_delete(f"{file_path_slave}.tmp")
                    ret = file_delete(file_path_slave)
                    if ret != OK:
                        return ERR, chg_flag
                    ret = copy_file(src_path=local_path_file, dest_path=file_path_slave)
                    if ret != OK:
                        return ERR, chg_flag
    # 仅配置ssh登录场景
    if ssh_login_config:
        chg_flag = True
    return OK, chg_flag


@ops_conn_operation
def get_syslog_config(ops_conn=None, ip_type='ipv4'):
    """Obtain the log server configuration."""
    ip_addresses = []
    uri = '/restconf/data?fields=/huawei-syslog:syslog/servers/server(ipaddress)'
    req_data = None
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ops_return_result(ret) or rsp_data == '':
        logging.warning('Failed to get information of syslog servers.')
        return ip_addresses

    root_elem = etree.fromstring(rsp_data)
    namespaces = {
        'syslog': 'urn:huawei:yang:huawei-syslog',
    }

    servers = root_elem.find("syslog:syslog/syslog:servers", namespaces)
    if servers is not None:
        for server in servers.findall("syslog:server", namespaces):
            elem = server.find("syslog:ipaddress", namespaces)
            if (elem is not None) and (elem.text is not None) and elem.text == ip_type:
                ip_addresses.append(elem.text)

    return ip_addresses


@ops_conn_operation
def set_syslog_config(ops_conn=None, ip_addresses=[], ipaddr_type='ipv4', syslog_trans=''):
    """Configure the log server."""
    syslog_tran = syslog_trans.lower()
    if syslog_tran in ['tcp']:
        for ip_address in ip_addresses:
            xpath = '/restconf/data/huawei-syslog:syslog/servers/server'
            str_temp = string.Template('''\
<server>
    <ip-type>$ip_type</ip-type>
    <ipaddress>$ip_addr</ipaddress>
    <is-default-vpn>true</is-default-vpn>
    <vrf-name>_public_</vrf-name>
    <level>debugging</level>
    <port>514</port>
    <facility>local2</facility>
    <channel-id>2</channel-id>
    <timestamp>UTC</timestamp>
    <transport-mode>$syslog_tran</transport-mode>
</server>
''')
            req_data = str_temp.substitute(ip_type=ipaddr_type, ip_addr=ip_address, syslog_tran=syslog_tran)
            ret, _, _ = ops_conn.set(xpath, req_data)
            if ops_return_result(ret):
                raise OPIExecError('Failed to change the transmission mode')
    return OK


@ops_conn_operation
def get_addr_by_hostname(host='', addr_type='1', ops_conn=None):
    """Convert the host name into an IP address."""

    print_ztp_log("Get IP address by host name...", LOG_INFO_TYPE)
    xpath = '{}{}'.format('/restconf/data/huawei-dns:dns/query-host-ips/query-host-ip=', host)
    req_data = None
    ret, _, rsp_data = ops_conn.get(xpath, req_data)
    if ops_return_result(ret):
        raise OPIExecError('Failed to get address by host name')

    root_elem = etree.fromstring(rsp_data)
    uriTmp = '{}'.format('/ip-address')
    uriTmp = uriTmp.replace('/', '/dns:')
    mpath = uriTmp[1:]
    namespaces = {'dns': 'urn:huawei:yang:huawei-dns'}
    elem = root_elem.find(mpath,namespaces)
    if elem is None:
        raise OPIExecError('Failed to get IP address by host name')

    return elem.text

@ops_conn_operation
def get_ipv6_addr_by_hostname(host='', ops_conn=None):
    print_ztp_log("Get IPv6 address by host name...", LOG_INFO_TYPE)
    xpath = '{}{}'.format('/restconf/data/huawei-dns:dns/query-host-ipv6s/query-host-ipv6=', host)
    req_data = None
    ret, _, rsp_data = ops_conn.get(xpath, req_data)
    if ops_return_result(ret):
        raise OPIExecError(f'Failed to get IPv6 address by host name reason={rsp_data}')

    root_elem = etree.fromstring(rsp_data)
    namespaces = {'dns': 'urn:huawei:yang:huawei-dns'}
    elem = root_elem.find('dns:ipv6-address', namespaces)
    if elem is None:
        raise OPIExecError('Failed to get IPv6 address by host name.')

    return elem.text


@ops_conn_operation
def set_environment(item_name, item_value, ops_conn=None):
    uri = "{}".format('/restconf/operations/huawei-sztp:operate-environment-variable')
    req_template = string.Template('''
                <input>
                    <item-name>$item_name</item-name>
                    <item-value>$item_value</item-value>
                </input>
                ''')
    req_data = req_template.safe_substitute(item_name=item_name, item_value=item_value)
    ret, _, rsp_data = ops_conn.create(uri, req_data)
    if ops_return_result(ret):
         logging.warning('Failed to set environment.')

    return OK

@ops_conn_operation
def get_environment(item_name, ops_conn=None):
    uri = "{}".format('/restconf/operations/huawei-sztp:operate-environment-variable')
    req_template = string.Template('''
                <input>
                    <item-name>$item_name</item-name>
                </input>
                ''')
    req_data = req_template.safe_substitute(item_name=item_name)
    ret, _, rsp_data = ops_conn.create(uri, req_data)
    if ops_return_result(ret) or rsp_data == '':
        print_ztp_log('Failed to get environment variables.', LOG_WARN_TYPE)
    elem = ""
    if "<itemvalue>" in rsp_data and "</itemvalue>" in rsp_data:
        elem = rsp_data.split("<itemvalue>")[1].split("</itemvalue>")[0].strip()
    return elem


@ops_conn_operation
def has_slave_mpu(ops_conn=None, mpu_slot={}):
    """Whether device has slave MPU, returns a bool value"""

    print_ztp_log("Test whether device has slave MPU...", LOG_INFO_TYPE)
    uri = '/restconf/data/huawei-devm:devm/physical-entitys/physical-entity=mpuModule'
    req_data = None

    has_slave = False
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ops_return_result(ret) or rsp_data == '':
        raise OPIExecError('Failed to get the device slave information')

    # Re-construct a packet for parsing.
    rsp_data_tmp = rsp_data.replace('<?xml version="1.0" encoding="UTF-8"?>','')
    rsp_data_tmp = rsp_data_tmp.replace(' xmlns="urn:huawei:yang:huawei-devm"','')
    rsp_data_tmp = '{}{}{}'.format(
        '<physical-entitys xmlns="urn:huawei:yang:huawei-devm">', rsp_data_tmp,
        '</physical-entitys>')
    root_elem = etree.fromstring(rsp_data_tmp)

    namespaces = {'devm': 'urn:huawei:yang:huawei-devm'}
    for entity in root_elem.findall("devm:physical-entity", namespaces):
        elem = entity.find("devm:standby-state", namespaces)
        if (elem is not None) and (elem.text is not None):
            if elem.text.lower().find('slave') >= 0:
                has_slave = True
                elem = entity.find("devm:position", namespaces)
                if elem is not None:
                    mpu_slot['slave'] = elem.text
            elif elem.text.lower().find('master') >= 0:
                elem = entity.find("devm:position", namespaces)
                if elem is not None:
                    mpu_slot['master'] = elem.text

    logging.info("device has slave: {} .".format(str(has_slave)))

    return has_slave


@ops_conn_operation
def get_system_info(ops_conn=None):
    """Get system info, returns a dict"""

    print_ztp_log("Get the system information...", LOG_INFO_TYPE)
    uri = '/restconf/data?fields=/huawei-system:system/system-info(product-name;esn;mac;product-version;uname)'
    req_data = None
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ops_return_result(ret) or rsp_data == '':
        raise OPIExecError('Failed to get the system information.')

    sys_info = {}.fromkeys(('product-name', 'esn', 'mac', 'product-version', 'uname'))
    root_elem = etree.fromstring(rsp_data)
    namespaces = {
        'system': 'urn:huawei:yang:huawei-system'
    }
    mpath = '{}'.format('system:system/system:system-info')
    nslen = len(namespaces['system'])
    elem = root_elem.find(mpath, namespaces)
    if elem is not None:
        for child in elem:
            tag = child.tag[nslen + 2:]  # skip the namespace, '{namespace}esn'
            if tag in list(sys_info.keys()):
                sys_info[tag] = child.text
    return sys_info


def convert_file_list_info(file_list):
    if not isinstance(file_list, list):
        return ""
    return ",".join(file_list)


def record_startup_info_to_file(startup_info, startup, real_config_name = None):
    """Record the startup information to file."""

    print_ztp_log("Record the current startup information to file...", LOG_INFO_TYPE)
    slog.syslog("Record the current startup information to file...", ops.INFORMATIONAL, ops.SYSLOG)
    sn_value = startup_info.get('*TIME_SN')
    sn_value = '' if sn_value in [None, 'DEFAULT'] else sn_value
    record_info = {}.fromkeys((FILE_TYPE_SOFTWARE, FILE_TYPE_CFG, FILE_TYPE_PAT,
                              FILE_TYPE_MOD, FILE_TYPE_FEATURE_PLUGIN, 'next_config'), '')
    rollback_val = 0
    for file_info in startup_info.get('FILE_INFO'):
        if file_info.get('*TYPE').lower() == FILE_TYPE_CFG and file_info.get('*EFFECTIVE_MODE') == EFFECTIVE_MODE_NO_REBOOT:
            rollback_val = 1
    if startup.current.image is not None:
        record_info[FILE_TYPE_SOFTWARE] = startup.current.image
    if startup.current.config is not None:
        record_info[FILE_TYPE_CFG] = startup.current.config
    if startup.current.patch is not None:
        record_info[FILE_TYPE_PAT] = startup.current.patch
    if startup.current.mod_list is not None:
        record_info[FILE_TYPE_MOD] = convert_file_list_info(startup.current.mod_list)
    if startup.current.feature_plugin_list is not None:
        record_info[FILE_TYPE_FEATURE_PLUGIN] = convert_file_list_info(startup.current.feature_plugin_list)
    if real_config_name is not None:
        record_info['next_config'] = real_config_name
    save_after_succ_val = get_save_after_success_by_config(startup_info)

    str_temp = string.Template('TIME_SN=$sn\n'
                               'SOFTWARE=$image_name\n'
                               'CFG=$config_name\n'
                               'PAT=$patch_name\n'
                               'MOD=$mod_list\n'
                               'FEATURE_IMAGE=$feature_image_name\n'
                               'SAVE_AFTER_SUCCESS=$save_after_succ\n'
                               'NEXT_CFG=$next_cfg\n'
                               'ROLLBACK_CFG=$rollback\n')

    startup_info_str = str_temp.substitute(sn=sn_value,
                                           image_name=record_info[FILE_TYPE_SOFTWARE],
                                           config_name=record_info[FILE_TYPE_CFG],
                                           patch_name=record_info[FILE_TYPE_PAT],
                                           mod_list=record_info[FILE_TYPE_MOD],
                                           feature_image_name=record_info[FILE_TYPE_FEATURE_PLUGIN],
                                           save_after_succ = save_after_succ_val,
                                           next_cfg = record_info['next_config'],
                                           rollback=rollback_val)
    print_ztp_log(f"Record the SAVE_AFTER_SUCCESS:{save_after_succ_val} to file.", LOG_INFO_TYPE)
    try:
        file_path = os.path.join(FLASH_HOME_PATH, STARTUP_INFO_FILE_NAME)
        if os.path.islink(file_path) != False:
            raise Exception("This is a soft link file. Please check.")

        with open(file_path, 'w', encoding='utf-8') as fhdl:
            fhdl.write(startup_info_str)
            os.fsync(fhdl)
        os.chmod(file_path,0o660)
    except Exception as reason:
        logging.error(reason)
        raise


def revert_file_list_info(file_info):
    return file_info.split(",")


def get_startup_info_from_file():
    """Get startup information from file"""

    print_ztp_log("Get the backup startup information from file...", LOG_INFO_TYPE)
    sn_value = ''
    startup_info_backup = {}.fromkeys((FILE_TYPE_SOFTWARE, FILE_TYPE_CFG, FILE_TYPE_PAT,
                                      FILE_TYPE_MOD, FILE_TYPE_FEATURE_PLUGIN, FILE_TYPE_SAVE_AFTER_SUCC), None)

    try:
        file_path = os.path.join(FLASH_HOME_PATH, STARTUP_INFO_FILE_NAME)
        if os.path.islink(file_path) != False:
            raise Exception("This is a soft link file. Please check.")

        with open(file_path, 'r', encoding='utf-8') as fhdl:
            fhdl.seek(0)
            lines_info = fhdl.readlines()
            for line in lines_info:
                if line.startswith('TIME_SN='):
                    sn_value = line[8:-1]
                elif line.startswith('SOFTWARE=') and line[9:-1] != '':
                    startup_info_backup[FILE_TYPE_SOFTWARE] = line[9:-1]
                elif line.startswith('CFG=') and line[4:-1] != '':
                    startup_info_backup[FILE_TYPE_CFG] = line[4:-1]
                elif line.startswith('PAT=') and line[4:-1] != '':
                    startup_info_backup[FILE_TYPE_PAT] = line[4:-1]
                elif line.startswith('MOD=') and line[4:-1] != '':
                    startup_info_backup[FILE_TYPE_MOD] = revert_file_list_info(line[4:-1])
                elif line.startswith('FEATURE_IMAGE=') and line[14:-1] != '':
                    startup_info_backup[FILE_TYPE_FEATURE_PLUGIN] = revert_file_list_info(line[14:-1])
                elif line.startswith('SAVE_AFTER_SUCCESS=') and line[19:-1] != '':
                    startup_info_backup[FILE_TYPE_SAVE_AFTER_SUCC] = line[19:-1]
                else:
                    continue
    except Exception as reason:
        logging.error(reason)
        raise

    return sn_value, startup_info_backup


def get_between_chars(s, char1, char2):
    start = s.find(char1) + len(char1)
    end = s.find(char2, start)
    if start > 0 and end > 0:
        return s[start:end]
    else:
        return ""


def set_file_effectiveMode(startup_info, sys_info):
    """Set the mode for activating version files.

    Traverse the information in the startup_info file and read the *EFFECTIVE_MODE field.
    If it has been set, no processing is required. If it is set to None, the default
    activation mode is used based on the file type. The system software package and
    configuration file take effect only after the device is restarted.Therefore, only the
    default activation mode can be configured for them. Activation is not required for
    customized files.
    """
    file_info_list = startup_info.get('FILE_INFO')
    if not isinstance(file_info_list, list):
        logging.error("Parameters is invalid.")
        return

    product_version = sys_info.get('product-version').upper()
    r_version = get_between_chars(product_version, 'R', 'C')
    c_version = get_between_chars(product_version, 'C', 'SP')
    if not r_version.isdigit() or not c_version.isdigit():
        return
    version = float(r_version + "." + c_version)

    for i in range(len(file_info_list)):
        file_type = file_info_list[i].get('*TYPE').lower()
        effective_mode = file_info_list[i].get('*EFFECTIVE_MODE')
        if effective_mode is None or file_type in [FILE_TYPE_SOFTWARE, FILE_TYPE_LIC, FILE_TYPE_USER] or \
                (file_type in [FILE_TYPE_PAT, FILE_TYPE_MOD, FILE_TYPE_FEATURE_PLUGIN] and effective_mode == EFFECTIVE_MODE_NO_NEED):
            file_info_list[i].update({
                '*EFFECTIVE_MODE': FILE_DEFAULT_EFFECTIVE_MODE.get(file_type.lower())
            })
        if file_type == FILE_TYPE_CFG and version < 24.1:
            file_info_list[i].update({'*EFFECTIVE_MODE': FILE_DEFAULT_EFFECTIVE_MODE.get(file_type.lower())})


def get_license_from_xml(esn, file_path_xml):
    """Obtain the license file that matches the ESN from the license file list.

    The license file name and SHA256 value of the file are returned.
    """
    if not isinstance(file_path_xml, str):
        logging.error("File path is invalid.")
        return None, None
    # Check the file name.
    file_name = os.path.basename(file_path_xml)
    file_path_real = os.path.join(FLASH_HOME_PATH, file_name)
    # Check whether the file exists.
    if not os.path.isfile(file_path_real):
        logging.error("File does not exist.")
        return None, None
    try:
        tree = etree.parse(file_path_real)
        # Obtain the root node.
        root = tree.getroot()
    except Exception as reason:
        logging.error(reason)
        raise

    for lic in root:
        for child in lic:
            if child.tag == "Esn" and child.text == esn:
                lic_name = lic.get("name")
                lic_sha256 = lic.get("sha256")
                if lic_sha256 == '':
                    lic_sha256 = None
                return lic_name, lic_sha256

    return None, None


@ops_conn_operation
def patch_active_proc(ops_conn=None, patch_name=''):
    """Activate the patch file."""

    print_ztp_log("Patch active...", LOG_INFO_TYPE)

    uri = '/restconf/operations/huawei-patch:load-patch'
    str_temp = string.Template('''\
<input>
    <name>$patchName</name>
    <load-type>run</load-type>
</input>
''')
    req_data = str_temp.substitute(patchName=patch_name)
    ret, _, _ = ops_conn.create(uri, req_data)
    if ops_return_result(ret):
        raise OPIExecError('Failed to execute the patch active operation.')

def cfg_deliver_proc(cfg_name):
    global system_reboot_needed
    if system_reboot_needed:
        return OK
    print_ztp_log("Start deliver config to device...", LOG_INFO_TYPE)
    ret = cli.rollback_cfg_to_file(cfg_name)
    return ret

@ops_conn_operation
def license_active_proc(ops_conn=None, license_name=''):
    """Activate the license file."""

    print_ztp_log("License active...", LOG_INFO_TYPE)
    uri = '/restconf/operations/huawei-license:license-active'
    str_temp = string.Template('''\
<input>
    <filename>$licenseName</filename>
</input>
''')
    req_data = str_temp.substitute(licenseName=license_name)
    ret, _, _ = ops_conn.create(uri, req_data)
    if ops_return_result(ret):
        print_ztp_log(f"Failed to execute the license active operation.", LOG_WARN_TYPE)


@ops_conn_operation
def delete_startup_patch_file(ops_conn=None):
    """Delete patch file for system to startup"""

    print_ztp_log("Delete the patch file...", LOG_INFO_TYPE)
    uri = '/restconf/operations/huawei-patch:delete-patch'
    req_data = '''\
<input>
    <delete-type>all</delete-type>
</input>
'''
    # it is a action operation, so use create for HTTP POST
    ret, _, rsp_data = ops_conn.create(uri, req_data)
    if ops_return_result(ret):
        logging.error("delete_startup_patch_file failed, rsp_data = \n{}".format(rsp_data))
        raise OPIExecError('Failed to delete patch.')


@ops_conn_operation
def get_active_intime(ops_conn=None):
    """通过ini中配置的激活延时时间获取具体需要延时的时间秒数"""
    time_sys = '0:0'
    uri = '/restconf/data?fields=/huawei-tm:tm/date-and-time(current-time)'
    req_data = None
    ret, _, rsp_data = ops_conn.get(uri, req_data)
    if ops_return_result(ret) or rsp_data == '':
        logging.warning("Get active in time failed!")
        return time_sys

    root_elem = etree.fromstring(rsp_data)
    namespaces = {'tm': 'urn:huawei:yang:huawei-tm'}
    elem = root_elem.find('tm:tm/tm:date-and-time/tm:current-time', namespaces)
    if elem is not None:
        text_list = re.findall(".*T(.*)Z.*", elem.text)
        if text_list is not None:
            text_list_member = text_list[0]
            time_sys = text_list_member[0:5]
    return time_sys


def get_active_intime_delay(active_in_time):

    if not isinstance(active_in_time, str):
        return None

    if re.match(r'^(0[0-9]|1[0-9]|2[0-3]|[0-9])\:(0[0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9]|[0-9])$', active_in_time):
        # 输入的是时间信息，例：'23:59'
        h_intime, m_intime = active_in_time.split(":")
        m_intime_count = int(h_intime) * ONEMINUTE + int(m_intime)

        time_now = get_active_intime()
        h_timenow, m_timenow = time_now.split(":")
        m_timenow_count = int(h_timenow) * ONEMINUTE + int(m_timenow)

        if m_intime_count > m_timenow_count:
            time_sleep = m_intime_count - m_timenow_count
            return time_sleep * ONEMINUTE
        else:
            time_sleep = m_intime_count + 24 * ONEMINUTE - m_timenow_count
            return time_sleep * ONEMINUTE
    else:
        logging.warning("The field of ACTIVE_INTIME is invalid!")
        return None


def get_delay_time_sec(active_delay_time):

    if not isinstance(active_delay_time, str):
        return None

    if re.match(r'(\d+)$', active_delay_time):
        # 输入的是延时时间信息，例，'60'
            delay_time_sec = int(active_delay_time)
            if delay_time_sec > (ONEHOUR * 24):
                logging.error("The active delay time over 24 hours!")
                delay_time_sec = ONEHOUR * 24
            return delay_time_sec
    else:
        logging.warning("The field of ACTIVE_DELAYTIME is invalid!")
        return None


def get_delay_time(active_delay_time, active_in_time):
    """通过ini中配置的激活延时时间或者指定文件生效时间获取具体需要延时的时间秒数"""

    print_ztp_log("Get activation delay time...", LOG_INFO_TYPE)
    if active_delay_time is None and active_in_time is None:
        return 0

    delay_time = get_delay_time_sec(active_delay_time)
    if delay_time is not None:
        return delay_time

    delay_time = get_active_intime_delay(active_in_time)
    if delay_time is not None:
        return delay_time

    logging.warning("Activation delay time is invalid!")
    return None


def sha256_calc(file_path, is_config_file=False):
    """Calculate the SHA256 value.

    input:  file_path       str     Path of the file for which the SHA256 needs to be calculated.
            is_config_file  int     Indicates whether a file is an intermediate file.
    output: ret             int     Indicates whether the calculation is successful.
            outStr          str     SHA256 value.
    """
    def read_chunks(fhdl):
        """read chunks"""
        chunk = fhdl.read(8096)
        while chunk:
            yield chunk
            chunk = fhdl.read(8096)
        else:
            fhdl.seek(0)

    if not isinstance(file_path, str):
        logging.error("File path is invalid.")
        return ERR, ""

    file_name = os.path.basename(file_path)
    file_path_real = os.path.join(FLASH_HOME_PATH, file_name)
    if os.path.islink(file_path_real) != False:
        raise Exception("This is a soft link file. Please check.")

    if not os.path.exists(file_path_real):
        logging.error("File does not exist.")
        return ERR, ""

    if is_config_file not in [True, False]:
        logging.error("The flag of config file is invalid. "
                      "is_config_file = {}".format(is_config_file))
        return ERR, ""

    sha256_obj = sha256()
    with open(file_path_real, "rb") as fhdl:
        if is_config_file is True:
            # skip the first line
            fhdl.seek(0)
            fhdl.readline()
        for chunk in read_chunks(fhdl):
            sha256_obj.update(chunk)

    sha256_value = sha256_obj.hexdigest()
    return OK, sha256_value


def get_file_info_str(file_info_list):
    if len(file_info_list) == 0:
        return None

    str_tmp = ''
    for file_info in file_info_list:
        str_tmp = '{}{}    {}'.format(str_tmp, '\n', str(file_info))

    return str_tmp


def get_file_infos_from_user_config(user_config_dict, sys_info):
    key_list = ['esn', 'mac', 'uname', 'product-name']
    for key in key_list:
        file_infos = user_config_dict.get(key, {})
        file_info = file_infos.get(sys_info.get(key), None)
        if file_info is not None:
            return key, file_infos
        comm_file = file_infos.get('COMMON', None)
        if comm_file is not None:
            return key, file_infos
    return None, None


def print_product_infos(sys_info):
    product_name = sys_info.get('product-name')
    product_esn = sys_info.get('esn')
    product_mac = sys_info.get('mac')
    product_uname = sys_info.get('uname')

    print_ztp_log(f"Product info of the device: product-name = '{product_name}', esn = '{product_esn}', "
                  f"mac = '{product_mac}', uname = '{product_uname}'.", LOG_INFO_TYPE)

def set_startup_info_from_user_config(startup_info, sys_info):
    startup_info.update({'*FILESERVER': FILE_SERVER})
    startup_info.update({'*TIME_SN': TIME_SN})
    startup_info.update({'SPACE_CLEAR': SPACE_CLEAR})
    startup_info.update({'SYSLOG_INFO': SYSLOG_INFO})
    startup_info.update({'DIRECTORY': ''})
    startup_info.update({'ACTIVE_DELAYTIME': ACTIVE_DELAYTIME})
    startup_info.update({'ACTIVE_INTIME': ACTIVE_INTIME})
    startup_info.update({'INSTALL_WEAK': INSTALL_WEAK})

    file_info_list = []
    print_product_infos(sys_info)
    global package_pool_flag
    # REMOTE_PACKAGE_POOL
    if len(REMOTE_PACKAGE_POOL) != 0:
        _key, _infos = get_file_infos_from_user_config(REMOTE_PACKAGE_POOL, sys_info)
        if _infos != None:
            package_info = _infos.get(sys_info.get(_key))
            if package_info != None:
                image_path = package_info.get('path')
                if image_path != None:
                    file_info = {}.fromkeys(
                        ('*FILENAME', '*TYPE', '*EFFECTIVE_MODE', 'ISBATCHPROCESS', 'SHA256', 'PATH'))
                    file_info['*FILENAME'] = os.path.basename(image_path)
                    file_info['PATH'] = image_path.lstrip('/')
                    if file_info['*FILENAME'] not in [None, '']:
                        file_info['*TYPE'] = FILE_TYPE_PACKAGE_POOL
                        file_info['*EFFECTIVE_MODE'] = EFFECTIVE_MODE_REBOOT
                        file_info['ISBATCHPROCESS'] = '0'
                        file_info['SHA256'] = package_info.get('sha256')
                        if file_info['SHA256'] == '':
                            file_info['SHA256'] = None
                        package_pool_flag =True
                        file_info_list.append(file_info)

    # REMOTE_IMAGE
    if len(REMOTE_IMAGE) != 0:
        _key, _infos = get_file_infos_from_user_config(REMOTE_IMAGE, sys_info)
        if _infos != None and not package_pool_flag:
            image_info = _infos.get(sys_info.get(_key))
            if image_info != None:
                image_path = image_info.get('path')
                if image_path != None:
                    file_info = {}.fromkeys(('*FILENAME', '*TYPE', '*EFFECTIVE_MODE', 'ISBATCHPROCESS', 'SHA256', 'PATH'))
                    file_info['*FILENAME'] = os.path.basename(image_path)
                    file_info['PATH'] = image_path.lstrip('/')
                    if file_info['*FILENAME'] not in [None, '']:
                        file_info['*TYPE'] = FILE_TYPE_SOFTWARE
                        file_info['*EFFECTIVE_MODE'] = EFFECTIVE_MODE_REBOOT
                        file_info['ISBATCHPROCESS'] = '0'
                        file_info['SHA256'] = image_info.get('sha256')
                        if file_info['SHA256'] == '':
                            file_info['SHA256'] = None

                        if ((VRPVER is not None) and (sys_info['product-version'].lower() == VRPVER.lower())):
                            logging.warning('The downloaded package version is the same as the current device package version, '
                                                'package download will be skipped')
                            pass
                        else:
                            file_info_list.append(file_info)

    # REMOTE_CONFIG
    if len(REMOTE_CONFIG) != 0:
        _key, _infos = get_file_infos_from_user_config(REMOTE_CONFIG, sys_info)
        if _infos != None:
            config_info = _infos.get(sys_info.get(_key))
            if config_info != None:
                config_path = config_info.get('path')
                if config_path != None:
                    file_info = {}.fromkeys(('*FILENAME', '*TYPE', '*EFFECTIVE_MODE', 'ISBATCHPROCESS', 'SHA256', 'PATH', 'SAVE_AFTER_SUCCESS'))
                    file_info['*FILENAME'] = os.path.basename(config_path)
                    file_info['PATH'] = config_path.lstrip('/')
                    if file_info['*FILENAME'] not in [None, '']:
                        file_info['*TYPE'] = FILE_TYPE_CFG
                        file_info['*EFFECTIVE_MODE'] = config_info.get('effective_mode')
                        if file_info['*EFFECTIVE_MODE'] in [None, '']:
                            file_info['*EFFECTIVE_MODE'] = EFFECTIVE_MODE_REBOOT
                        file_info['ISBATCHPROCESS'] = '0'
                        file_info['SHA256'] = config_info.get('sha256')
                        if file_info['SHA256'] == '':
                            file_info['SHA256'] = None
                        file_info['SAVE_AFTER_SUCCESS'] = config_info.get('save_after_success')
                        file_info_list.append(file_info)
                        disable_ssh_login_config()
            else:
                config_info = _infos.get('COMMON')
                if config_info is not None and config_info != '':
                    config_path = config_info.get('path') % sys_info.get(_key)
                    if config_path is not None:
                        file_info = {}.fromkeys(
                            ('*FILENAME', '*TYPE', '*EFFECTIVE_MODE', 'ISBATCHPROCESS', 'SHA256', 'PATH',
                            'SAVE_AFTER_SUCCESS'))
                        file_info['*FILENAME'] = os.path.basename(config_path)
                        file_info['PATH'] = config_path.lstrip('/')
                        if file_info['*FILENAME'] not in [None, '']:
                            file_info['*TYPE'] = FILE_TYPE_CFG
                            file_info['*EFFECTIVE_MODE'] = config_info.get('effective_mode')
                            if file_info['*EFFECTIVE_MODE'] in [None, '']:
                                file_info['*EFFECTIVE_MODE'] = EFFECTIVE_MODE_REBOOT
                            file_info['ISBATCHPROCESS'] = '0'
                            file_info['SHA256'] = config_info.get('sha256')
                            if file_info['SHA256'] == '':
                                file_info['SHA256'] = None
                            file_info['SAVE_AFTER_SUCCESS'] = config_info.get('save_after_success')
                            file_info_list.append(file_info)
                            disable_ssh_login_config()

    # REMOTE_PATCH
    if len(REMOTE_PATCH) != 0:
        _key, _infos = get_file_infos_from_user_config(REMOTE_PATCH, sys_info)
        if _infos != None:
            patch_info = _infos.get(sys_info.get(_key))
            if patch_info != None:
                patch_path = patch_info.get('path')
                if patch_path != None:
                    file_info = {}.fromkeys(('*FILENAME', '*TYPE', '*EFFECTIVE_MODE', 'ISBATCHPROCESS', 'SHA256', 'PATH'))
                    file_info['*FILENAME'] = os.path.basename(patch_path)
                    file_info['PATH'] = patch_path.lstrip('/')
                    if file_info['*FILENAME'] not in [None, '']:
                        file_info['*TYPE'] = FILE_TYPE_PAT
                        file_info['*EFFECTIVE_MODE'] = patch_info.get('effective_mode')
                        if file_info['*EFFECTIVE_MODE'] in [None, '']:
                            file_info['*EFFECTIVE_MODE'] = EFFECTIVE_MODE_NO_REBOOT
                        file_info['ISBATCHPROCESS'] = '0'
                        file_info['SHA256'] = patch_info.get('sha256')
                        if file_info['SHA256'] == '':
                            file_info['SHA256'] = None
                        file_info_list.append(file_info)

    # REMOTE_MOD
    if len(REMOTE_MOD) != 0:
        _key, _infos = get_file_infos_from_user_config(REMOTE_MOD, sys_info)
        if _infos != None:
            patch_info = _infos.get(sys_info.get(_key))
            if patch_info != None:
                patch_path = patch_info.get('path')
                if patch_path != None:
                    file_info = {}.fromkeys(('*FILENAME', '*TYPE', '*EFFECTIVE_MODE', 'ISBATCHPROCESS', 'SHA256', 'PATH'))
                    file_info['*FILENAME'] = os.path.basename(patch_path)
                    file_info['PATH'] = patch_path.lstrip('/')
                    if file_info['*FILENAME'] not in [None, '']:
                        file_info['*TYPE'] = FILE_TYPE_MOD
                        file_info['*EFFECTIVE_MODE'] = patch_info.get('effective_mode')
                        if file_info['*EFFECTIVE_MODE'] in [None, '']:
                            file_info['*EFFECTIVE_MODE'] = EFFECTIVE_MODE_NO_REBOOT
                        file_info['ISBATCHPROCESS'] = '0'
                        file_info['SHA256'] = patch_info.get('sha256')
                        if file_info['SHA256'] == '':
                            file_info['SHA256'] = None
                        file_info_list.append(file_info)


    if len(REMOTE_FEATURE_PLUGIN) != 0:
        _key, _infos = get_file_infos_from_user_config(REMOTE_FEATURE_PLUGIN, sys_info)
        if _infos != None:
            patch_info = _infos.get(sys_info.get(_key))
            if patch_info != None:
                patch_path = patch_info.get('path')
                if patch_path != None:
                    file_info = {}.fromkeys(('*FILENAME', '*TYPE', '*EFFECTIVE_MODE', 'ISBATCHPROCESS', 'SHA256', 'PATH'))
                    file_info['*FILENAME'] = os.path.basename(patch_path)
                    file_info['PATH'] = patch_path.lstrip('/')
                    if file_info['*FILENAME'] not in [None, '']:
                        file_info['*TYPE'] = FILE_TYPE_FEATURE_PLUGIN
                        file_info['*EFFECTIVE_MODE'] = patch_info.get('effective_mode')
                        if file_info['*EFFECTIVE_MODE'] in [None, '']:
                            file_info['*EFFECTIVE_MODE'] = EFFECTIVE_MODE_NO_REBOOT
                        file_info['ISBATCHPROCESS'] = '0'
                        file_info['SHA256'] = patch_info.get('sha256')
                        if file_info['SHA256'] == '':
                            file_info['SHA256'] = None
                        file_info_list.append(file_info)

    if len(REMOTE_BAT) != 0:
        _key, _infos = get_file_infos_from_user_config(REMOTE_BAT, sys_info)
        if _infos != None:
            patch_info = _infos.get(sys_info.get(_key))
            if patch_info != None:
                patch_path = patch_info.get('path')
                if patch_path != None:
                    file_info = {}.fromkeys(('*FILENAME', '*TYPE', '*EFFECTIVE_MODE', 'ISBATCHPROCESS', 'SHA256', 'PATH'))
                    file_info['*FILENAME'] = os.path.basename(patch_path)
                    file_info['PATH'] = patch_path.lstrip('/')
                    if file_info['*FILENAME'] not in [None, '']:
                        file_info['*TYPE'] = FILE_TYPE_SCRIPT
                        file_info['*EFFECTIVE_MODE'] = patch_info.get('effective_mode')
                        if file_info['*EFFECTIVE_MODE'] in [None, '']:
                            file_info['*EFFECTIVE_MODE'] = EFFECTIVE_MODE_NO_REBOOT
                        file_info['ISBATCHPROCESS'] = '0'
                        file_info['SHA256'] = patch_info.get('sha256')
                        if file_info['SHA256'] == '':
                            file_info['SHA256'] = None
                        file_info_list.append(file_info)

    # REMOTE_LICLIST
    license_info = REMOTE_LICLIST
    license_path = license_info.get('path')
    if license_path != None:
        file_info = {}.fromkeys(('*FILENAME', '*TYPE', '*EFFECTIVE_MODE', 'ISBATCHPROCESS', 'SHA256', 'PATH'))
        file_info['*FILENAME'] = os.path.basename(license_path)
        file_info['PATH'] = license_path.lstrip('/')
        if file_info['*FILENAME'] not in [None, '']:
            file_info['*TYPE'] = FILE_TYPE_LIC
            file_info['*EFFECTIVE_MODE'] = EFFECTIVE_MODE_NO_REBOOT
            file_info['ISBATCHPROCESS'] = '1'
            file_info['SHA256'] = license_info.get('sha256')
            if file_info['SHA256'] == '':
                file_info['SHA256'] = None
            file_info_list.append(file_info)

    # REMOTE_USER
    if len(REMOTE_USER) != 0:
        _key, _infos = get_file_infos_from_user_config(REMOTE_USER, sys_info)
        if _infos != None:
            user_info_list = _infos.get(sys_info.get(_key))
            if user_info_list != None:
                for user_info in user_info_list:
                    if len(file_info_list) >= 9:
                        logging.warning("Too many user files, please check!")
                        break
                    user_path = user_info.get('path')
                    if user_path != None:
                        file_info = {}.fromkeys(('*FILENAME', '*TYPE', '*EFFECTIVE_MODE', 'ISBATCHPROCESS', 'SHA256', 'PATH'))
                        file_info['*FILENAME'] = os.path.basename(user_path)
                        file_info['PATH'] = user_path.lstrip('/')
                        if file_info['*FILENAME'] not in [None, '']:
                            file_info['*TYPE'] = FILE_TYPE_USER
                            file_info['*EFFECTIVE_MODE'] = EFFECTIVE_MODE_NO_NEED
                            file_info['ISBATCHPROCESS'] = '0'
                            file_info['SHA256'] = user_info.get('sha256')
                            if file_info['SHA256'] == '':
                                file_info['SHA256'] = None
                            file_info_list.append(file_info)

    print_ztp_log(f"The device deployment file infos: {get_file_info_str(file_info_list)}.", LOG_INFO_TYPE)
    startup_info.update({'FILE_INFO': file_info_list})


def check_parameter(aset):
    seq = ['&', '>', '<', '"', "'", "|", '`', '$', ';', '(', ')', '[', ']', '{', '}', '~', '*', '?']
    if aset:
        for c in seq:
            if c in aset:
                return True
    return False


def check_number(aset):
    nums = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']
    if aset:
        for num in aset:
            if num not in nums:
                return True
    return False


def check_filename_and_extension(startup_info):
    file_info_list = startup_info.get('FILE_INFO')
    for file_info in file_info_list:
        file_name = file_info.get('*FILENAME')
        file_type = file_info.get('*TYPE')
        if file_name not in ['', None] and check_parameter(file_name):
            raise ZTPErr('Invalid filename of {} file, the name should not contain: {} {} {} {} {} {} {} {} .'\
                .format(file_type, '&', '>', '<', '"', "'", "|", '`', '$'))
        _, ext = os.path.splitext(file_name)
        if (file_type != FILE_TYPE_USER) and (ext.lower() not in FILE_EXTENSION.get(file_type)):
            raise ZTPErr('Invalid filename extension of {} file.'.format(file_type))

def get_save_after_success_by_config(startup_info):
    file_info_list = startup_info.get('FILE_INFO')
    for file_info in file_info_list:
        file_type = file_info.get('*TYPE')
        if file_type != FILE_TYPE_CFG:
            continue
        if file_info.get('SAVE_AFTER_SUCCESS') == SAVE_AFTER_SUCC_NO:
            return SAVE_AFTER_SUCC_NO
    return SAVE_AFTER_SUCC_YES

def check_SN_config(startup_info):
    sn = startup_info.get('*TIME_SN')
    if sn is None or sn == "":
        return
    if not isinstance(sn, str):
        raise ZTPErr('Invalid type of TIME_SN value.')
    if len(sn) != 14:
        raise ZTPErr('Invalid length of TIME_SN value.')
    if check_number(sn):
        raise ZTPErr('Invalid value of TIME_SN, the value should only contain numbers.')


def check_user_config(startup_info):
    check_filename_and_extension(startup_info)
    check_SN_config(startup_info)


def check_starupinfo_txt():
    if not file_exist(file_path=STARTUP_INFO_FILE_NAME):
        return

    # Obtain information from the file.
    sn_from_file, _ = get_startup_info_from_file()
    if TIME_SN == "" or TIME_SN != sn_from_file:
        return

    # Obtain the current deployment status flag.
    ztp_status = get_environment(ZTP_ENABLEFLAG)
    if ztp_status == str(ZTP_STATUS_END):
        # Exit the ZTP process. The device starts.
        print_ztp_log('The current device was successfully deployed last time, '
                        'and the TIME_SN configured this time is the same as that of the last time. '
                        'Please check!', LOG_WARN_TYPE)
        if g_is_usb_startup:
            raise ZTPTimesnRepeat('There is no need to continue usb process!')
        else:
            raise ZTPErr('There is no need to continue!')
    elif ztp_status == str(ZTP_STATUS_RUNNING):
        # The device restarts unexpectedly during the last deployment.
        print_ztp_log('The previous deployment is not complete '
                        'and the TIME_SN configured this time is the same as that configured last time,'
                        'continue the deployment.', LOG_WARN_TYPE)
        return


def check_if_reboot_needed(startup_info):
    file_info_list = startup_info.get('FILE_INFO')
    if not isinstance(file_info_list, list):
        logging.error("The type of FILE_INFO is invalid.")
        return True

    reboot_flag = False
    for i in range(len(file_info_list)):
        effective_mode = file_info_list[i].get('*EFFECTIVE_MODE')
        if effective_mode == EFFECTIVE_MODE_REBOOT:
            reboot_flag = True
            break

    return reboot_flag


@ops_conn_operation
def set_master_key(masterkey='', ops_conn=None):
    """set masterkey"""

    print_ztp_log('Now set master key...', LOG_INFO_TYPE)
    is_master_key = ops.opscharacterEncode(masterkey)
    uri = '{}'.format('/restconf/operations/huawei-masterkey:set-masterkey')
    if is_master_key == '':
        req_data =  """<input> </input>"""
    else:
        req_template = string.Template('''
            <input>
                <new-masterkey>$newmasterkey</new-masterkey>
            </input>
            ''')
        req_data = req_template.substitute(newmasterkey=is_master_key)
    ret, _, rsp_data = ops_conn.create(uri, req_data)
    if ops_return_result(ret):
        return ERR, rsp_data
    return OK, ''


def record_clear_master_key_to_file():
    """Record the startup information to file."""

    print_ztp_log("Record clear master key to file...", LOG_INFO_TYPE)
    try:
        file_path = os.path.join(FLASH_HOME_PATH, SET_MASTER_FILE_NAME)

        if os.path.islink(file_path) != False:
            raise Exception("This is a soft link file. Please check.")

        with open(file_path, 'w', encoding='utf-8') as fhdl:
            os.fsync(fhdl)
        os.chmod(file_path,0o660)
    except Exception as reason:
        logging.error(reason)
        raise


def copy_mod_file_to_dest(mod_name):
    if mod_name is None:
        return OK

    src_file_path = f'flash:/{mod_name}'
    dest_file_path = f'flash:/$_install_mod/{mod_name}'
    ret = file_delete(dest_file_path)
    if ret != OK:
        return ERR
    ret = copy_file(src_file_path, dest_file_path)
    if ret != OK:
        return ERR
    return OK


def check_addr(address):
    try:
        version = ipaddress.ip_address(address).version
        if version == 4:
            return 'DHCPv4'
        elif version == 6:
            return 'DHCPv6'
        else:
            return None
    except Exception as e:
        return None


def check_filserver_dhcp_type(url):
    url_tuple = urlparse(url)
    ipaddr = url_tuple.hostname
    cur_type = check_addr(ipaddr)
    return cur_type


def clean_download_temp_file(file_path):
    ret1 = file_delete(file_path)
    ret2 = file_delete(f"{file_path}.tmp")
    if ret1 != OK or ret2 != OK:
        return ERR
    return OK

def record_mark_file(filename=''):
    try:
        file_path = os.path.join(FLASH_HOME_PATH, filename)
        if os.path.islink(file_path) != False:
            raise Exception("This is a soft link file. Please check.")
        with open(file_path, 'w', encoding='utf-8') as fhdl:
            fhdl.write(" ")
            os.fsync(fhdl)
        os.chmod(file_path, 0o660)
    except Exception as reason:
        print_ztp_log(reason, LOG_ERROR_TYPE)
        raise

def check_user_weakea_feature(param=None):
    if param not in [1, 0, None]:
        logging.warning("INSTALL_WEAK information is not right.")
    if param == 1:
        return None
    else:
        return 0
    return None


def check_software_in_ini(startup_info):
    softwareflag = False
    length = len(startup_info['FILE_INFO'])
    for _len in range(length):
        file_type = startup_info['FILE_INFO'][_len]['*TYPE']
        if file_type.upper() == 'SOFTWARE' or package_pool_flag:
            softwareflag = True
    return softwareflag


def get_dev_ip():
    ip_addr, mask = get_interface_ip('Vlanif1')
    return ip_addr

def get_dev_port():
    return 'Vlanif1'

def get_dev_esn():
    system_info = get_system_info()
    return system_info.get('esn', '')


def get_dev_mac():
    system_info = get_system_info()
    return system_info.get('mac', '')


def get_dev_software():
    startup = Startup()
    return startup.current.image


def get_dev_patch():
    startup = Startup()
    return startup.current.patch


def exec_user_comman(sys_info):
    command_list = []
    _key, _infos = get_file_infos_from_user_config(USER_COMMAND, sys_info)
    if _infos != None:
        command_list = _infos.get(sys_info.get(_key))
    print_ztp_log(f"begin exec cli", LOG_INFO_TYPE)
    if command_list is None:
        return OK
    for cli_list in command_list:
        ret, result = cli.execute_cli_list(cli_list)
        if ret != OK:
            print_ztp_log(f"exec cli {cli_list} failed, reason is {result}", LOG_ERROR_TYPE)
            return ret
    return OK

def del_all_tmp_file(slave_paths_flash):
    """ 删除所有下载的文件和临时生成的文件 """

    file_list = ZTP_DOWNLOAD_FILE_LIST.copy()
    for file in file_list:
        ret = check_parameter(file)
        if ret != OK:
            ZTP_DOWNLOAD_FILE_LIST.remove(file)
            print_ztp_log(f"Invalid filename, the name should not contain: {INVALID_CHARACTERS_STR}", LOG_WARN_TYPE)
        file_delete(file)
        if os.path.splitext(file)[-1].lower() == '.mod':
            file_delete(f'flash:/$_install_mod/{file}')

    if len(slave_paths_flash) > 0:
        del_download_file_list = {}
        for path in slave_paths_flash:
            del_download_file_list.update({path: ZTP_DOWNLOAD_FILE_LIST})

        del_list_file(del_download_file_list, [])

    if system_startupInfo_state:
        file_delete(file_path=STARTUP_INFO_FILE_NAME)

def main_proc():
    """Main processing"""

    print_ztp_log("Start ztp_script...", LOG_INFO_TYPE)
    sys_info = get_system_info()
    startup = Startup()
    mpu_slot = {}.fromkeys(('master', 'slave'))
    slave = has_slave_mpu(mpu_slot=mpu_slot) # Check whether a slave MPU exists.

    # Generate startup information based on the user configuration.
    startup_info = {}
    set_startup_info_from_user_config(startup_info, sys_info)

    # Check the user input configuration.
    check_user_config(startup_info)

    # Configure the log server based on the configured log transfer protocol.
    syslog_trans_protocol = startup_info.get('SYSLOG_INFO')
    addr_type = 'ipv4'
    if DHCP_TYPE == 'DHCPv6':
        addr_type = 'ipv6'
    ip_addresses = get_syslog_config(ip_type=addr_type)
    set_syslog_config(ip_addresses=ip_addresses, ipaddr_type=addr_type, syslog_trans=syslog_trans_protocol)

    check_starupinfo_txt()
    global system_startupInfo_state
    system_startupInfo_state = SYSTEM_STARUPINFO_END

    # Check the flash memory space.
    softwareflag = check_software_in_ini(startup_info)
    ret = check_space(startup_info, startup.current.image, softwareflag)
    if ret is ERR:
        slog.syslog("Error: the space is not enough.", ops.ERROR, ops.SYSLOG)
        raise ZTPErr('The space is not enough.')

    # Set the ZTP deployment status to 0.
    set_environment(ZTP_ENABLEFLAG, ZTP_STATUS_RUNNING)

    url = startup_info['*FILESERVER']
    cur_dhcp_type = check_filserver_dhcp_type(url)
    if cur_dhcp_type is not None and cur_dhcp_type != DHCP_TYPE:
        print_ztp_log("The IP version in ini file is inconsistant with bootfile server.", LOG_ERROR_TYPE)
        return ERR

    # Obtain the version file list and names.
    global install_weakea_feature
    install_weakea_feature = check_scheme_install_weakea(url, startup_info.get('INSTALL_WEAK'))
    file_list, file_name_dict = ztp_get_file_list(startup, sys_info, startup_info)
    slog.syslog('The device of system mac %s, ESN %s begins to download file.' %(sys_info['mac'], sys_info['esn']), ops.INFORMATIONAL, ops.SYSLOG)
    # Activate the file.
    delay_time_sec = get_delay_time(startup_info.get('ACTIVE_DELAYTIME'), startup_info.get('ACTIVE_INTIME'))

    if delay_time_sec == None:
        slog.syslog("Get delay time failed.", ops.INFORMATIONAL, ops.SYSLOG)
        return ERR
    # Download the version files.
    ret, chg_flag= ztp_file_download(file_list, startup_info, slave)
    if ret != OK or chg_flag is False:
        return ERR

    if install_weakea_feature is not None:
        install_weakea_feature = check_user_weakea_feature(startup_info.get('INSTALL_WEAK'))

    if install_weakea_feature is not None:
        install_weakea_feature = None
        uninstall_weakea_feature()

     # Set the mode for activating the file.
    set_file_effectiveMode(startup_info, sys_info)
    global system_reboot_needed
    system_reboot_needed = check_if_reboot_needed(startup_info)

    image_name      = file_name_dict.get(FILE_TYPE_SOFTWARE)
    config_name     = file_name_dict.get(FILE_TYPE_CFG)
    patch_name      = file_name_dict.get(FILE_TYPE_PAT)
    mod_name        = file_name_dict.get(FILE_TYPE_MOD)
    feature_name    = file_name_dict.get(FILE_TYPE_FEATURE_PLUGIN)
    if ztp_smart_load_name is not None:
        image_name = ztp_smart_load_name
    # Activate the file.
    print_ztp_log(f"After {delay_time_sec} seconds activation will be performed.", LOG_INFO_TYPE)
    slog.syslog("After {} seconds activation will be performed.".format(delay_time_sec), ops.INFORMATIONAL, ops.SYSLOG)
    sleep(delay_time_sec)
    # copy the mod file.
    ret = copy_mod_file_to_dest(mod_name)
    if ret != OK:
        logging.error("Failed to copy mod file to destination path.")
        return ERR

    # set masterkay
    if master_exportcfg is None and config_name is not None and is_set_master is not None :
        ret, _= set_master_key(is_set_master)
        _, nextcfg = startup.get_startup_info_by_type(FILE_TYPE_CFG)
        if nextcfg is not None:
            startup._del_startup_config_file()
        if ret == OK:
            print_ztp_log('Now set master key success...', LOG_INFO_TYPE)
        else:
            raise ZTPErr('Failed to set master key.')

        if is_clear_master == True:
            record_clear_master_key_to_file()
            ZTP_DOWNLOAD_FILE_LIST.append(SET_MASTER_FILE_NAME)


    file_info_list = startup_info.get('FILE_INFO')
    if not isinstance(file_info_list, list):
        logging.error("Parameters is invalid.")
        return ERR

    for file_info in file_info_list:
        effective_mode = file_info.get('*EFFECTIVE_MODE')
        if effective_mode != EFFECTIVE_MODE_NO_REBOOT:
            continue

        file_type = file_info.get('*TYPE').lower()
        if file_type == FILE_TYPE_PAT:
            patch_name = None

        if file_type == FILE_TYPE_MOD:
            mod_name = None

        if file_type == FILE_TYPE_FEATURE_PLUGIN:
            feature_name = None

    startup.set_exportcfg(master_exportcfg)

    ret = exec_user_comman(sys_info)
    if ret != OK:
        return ERR

    # Record the current startup and configuration information to a file for new deployment.
    record_startup_info_to_file(startup_info, startup)

    # Specify the version files for the next startup.
    startup.set_startup_info(image_name, config_name, patch_name, mod_name, feature_name, slave)
    global system_file_state
    system_file_state = SYSTEM_FILE_SETTING_END

    startup.file_effective_proc(file_info_list, file_name_dict, slave)
    set_ssh_network_config()
    http_post_device_info()

    scripts_name = file_name_dict.get(FILE_TYPE_SCRIPT)
    if isinstance(scripts_name, str):
        # STACK_ZTP 设置为True是组堆叠场景,stack enable会自动把当前配置save到下次配置文件中
        # 需要先执行回滚到对应配置文件，然后清掉设置的下次启动配置文件
        if STACK_ZTP == True and config_name is None:
            startup.reset_startup_info(slave)
            del_all_tmp_file(flash_home_path_slave)
            raise ZTPErr("The configuration file must be not None in the stack process.")
        if STACK_ZTP == True and config_name is not None:
            ret = cli.rollback_cfg_to_file(config_name)
            if ret == ERR:
                startup.reset_startup_info(slave)
                raise ZTPErr(f"Rollback configuration file {config_name} failed")
            record_startup_info_to_file(startup_info, startup, config_name)
            startup.clean_next_config_file()
        print_ztp_log(f"Start to execute bat file({scripts_name})...", LOG_INFO_TYPE)
        ret, result = cli.execute_bat_file(scripts_name)
        if ret != OK:
            # 堆叠场景执行bat脚本失败了需要等待3分钟后重启
            startup.reset_startup_info(slave)
            del_all_tmp_file(flash_home_path_slave)
            if STACK_ZTP == True and config_name is not None:
                print_ztp_log(f"Failed to execute bat file({scripts_name}) and wait 3 minutes to reboot.",
                              LOG_INFO_TYPE)
                sleep(180)
                ret, _ = reboot_system()
                if ret == ERR:
                    raise Exception('Failed to execute the reboot system operation.')
                sleep(300)
            raise ZTPErr(f"execute bat file failed, reason={result}")
        if STACK_ZTP == True and config_name is not None:
            # 如果bat脚本没自动重启，则设置下次启动配置文件
            startup.set_startup_info(image_file=None, config_file=config_name, patch_file=None,
                                    mod_file=None, feature_plugin=None, slave = slave)
        print_ztp_log("The bat file executed successfully.", LOG_INFO_TYPE)

    if check_ztp_status_is_disable():
        startup.reset_startup_info(slave)
        raise ZTPDisableAbort()
    startup.cfg_effective_proc(file_info_list, config_name, slave) # 配置文件零重启激活放在所有操作最后
    return OK


def main(download_file_list=[], logfile_name=''):
    """The main function of user script. It is called by ZTP frame, so do not remove or change this function.

    Args:
    Raises:
    Returns: user script processing result
    """
    try:
        global LOG_FILE
        LOG_FILE = logfile_name
        global flash_home_path_master
        global flash_home_path_slave
        global usb_home_path
        global g_is_usb_startup
        ret = ERR
        flash_home_path_master, flash_home_path_slave, _ = get_home_path()
        if isinstance(download_file_list, str):
            usb_home_path = download_file_list
            g_is_usb_startup = True
        ret = main_proc()
        # 仅配置ssh_login_config场景，期望保留开局口申请的ip，用作客户ssh
        if not system_reboot_needed and ssh_login_config:
            os._exit(0)
            print_ztp_log("Script run success, scrip exit(0)", LOG_INFO_TYPE)
    except ZTPAbort as reason:
        raise ZTPAbort(reason)

    except ZTPTimesnRepeat as reason:
        raise ZTPTimesnRepeat(reason)

    except ZTPRollback as reason:
        raise ZTPRollback(reason)

    except OPIExecError as reason:
        print_ztp_log(f"OPI execute error: {str(reason)}", LOG_ERROR_TYPE)
        ret = ERR

    except ZTPErr as reason:
        print_ztp_log(f"ZTP error: {str(reason)}", LOG_ERROR_TYPE)
        ret = ERR

    except IOError as reason:
        print_ztp_log(f"{str(reason)}", LOG_ERROR_TYPE)
        ret = ERR

    except ZTPDisableAbort as reason:
        logging.warning('The user executed the set ztp disable command line.')
        ret = ERR

    except Exception as reason:
        print_ztp_log(f"{str(reason)}", LOG_ERROR_TYPE)
        traceinfo = traceback.format_exc()
        logging.error(traceinfo)
        ret = ERR

    finally:
        if install_weakea_feature is not None:
            uninstall_weakea_feature()
        if isinstance(download_file_list, list):
            download_file_list.extend(ZTP_DOWNLOAD_FILE_LIST)
        elif ret == ERR:
            del_all_tmp_file(flash_home_path_slave)

    return ret, (system_file_state, system_startupInfo_state, system_reboot_needed)


if __name__ == "__main__":
    main()
