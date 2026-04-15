# 心率监测 Android APP

基于 Kivy 框架开发的 Android 心率监测应用，用于接收 ESP01 通过 WiFi 发送的极简心率数据。

## 功能特性

- ✅ 自动连接 ESP01 WiFi（AP 模式）
- ✅ 实时显示心率、血氧数据
- ✅ 动态波形图绘制
- ✅ 异常状态报警
- ✅ 本地数据缓存
- ✅ 断线自动重连
- ✅ 抗弱网、抗丢包设计

## 协议格式

ESP01 发送数据格式（极简、无 HTTP、无 JSON）：
```
心率,血氧,状态\n
```

示例：
```
78,95,0
120,88,1
45,92,2
```

状态码：
- `0` - 正常
- `1` - 注意（轻微异常）
- `2` - 警告（严重异常）

## 项目结构

```
HeartRateApp/
├── main.py              # 主应用代码
├── heart_rate.kv        # Kivy 界面定义
├── data_processor.py    # 数据处理模块
├── buildozer.spec       # APK 打包配置
├── requirements.txt    # Python 依赖
└── README.md           # 说明文档
```

## 快速开始

### 1. 安装依赖（PC 测试）

```bash
pip install kivy
```

### 2. 运行应用（PC 测试）

```bash
cd HeartRateApp
python main.py
```

### 3. 打包 APK（需要 Linux 环境）

#### 方法一：使用 WSL（Windows 用户）

```bash
# 安装 WSL
wsl --install -d Ubuntu

# 在 WSL 中安装依赖
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev automake

# 安装 Buildozer
pip3 install buildozer cython

# 克隆项目（或复制项目文件到 WSL）
cd ~
# 复制 HeartRateApp 文件夹到 WSL

# 打包 APK
cd HeartRateApp
buildozer android debug
```

#### 方法二：使用 Docker（推荐）

```bash
# 拉取 Buildozer Docker 镜像
docker pull kivy/buildozer

# 运行容器并打包
docker run --rm -v "路径/HeartRateApp":/app kivy/buildozer android debug
```

#### 方法三：使用 GitHub Actions（最简单）

1. 将项目上传到 GitHub
2. 创建 `.github/workflows/build.yml`：

```yaml
name: Build APK
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build with Buildozer
        uses: ArtemSBulgakov/buildozer-action@v1
        id: buildozer
        with:
          workdir: .
          buildozer_version: stable
      - name: Upload APK
        uses: actions/upload-artifact@v3
        with:
          name: heartratemonitor
          path: ${{ steps.buildozer.outputs.filename }}
```

3. 推送代码后，在 Actions 页面下载生成的 APK

### 4. 安装 APK

将生成的 APK 文件传输到 Android 手机并安装：
- 位置：`bin/heart_rate_monitor-1.0.0-arm64-v8a-debug.apk`
- 首次安装需要允许"安装未知来源应用"

## ESP01 配置

### WiFi AP 模式配置

ESP01 作为 AP 热点，手机连接后直接通信：

```cpp
// ESP01 Arduino 代码示例
#include <ESP8266WiFi.h>

const char* ssid = "HeartRateMonitor";
const char* password = "12345678";

WiFiServer server(8080);

void setup() {
  Serial.begin(115200);
  
  // 配置为 AP 模式
  WiFi.softAP(ssid, password);
  
  server.begin();
  Serial.println("AP Started");
  Serial.println(WiFi.softAPIP()); // 默认 192.168.4.1
}

void loop() {
  WiFiClient client = server.available();
  
  if (client) {
    while (client.connected()) {
      // 从 STM32 读取心率数据
      if (Serial.available()) {
        String data = Serial.readStringUntil('\n');
        // 发送到手机
        client.println(data);
      }
      delay(10);
    }
    client.stop();
  }
}
```

### 数据发送格式

STM32 通过串口发送给 ESP01：
```cpp
Serial1.print(heartRate);
Serial1.print(",");
Serial1.print(spo2);
Serial1.print(",");
Serial1.println(status);
```

## 连接配置

在 `main.py` 中修改连接参数：

```python
ESP01_IP = '192.168.4.1'      # ESP01 AP 模式默认 IP
ESP01_PORT = 8080              # 监听端口
WIFI_SSID = 'HeartRateMonitor'  # WiFi 名称
WIFI_PASSWORD = '12345678'      # WiFi 密码
```

## 使用流程

1. **启动 ESP01**：ESP01 上电后创建 WiFi 热点
2. **连接 WiFi**：手机连接到 `HeartRateMonitor` WiFi
3. **打开 APP**：启动心率监测 APP
4. **点击连接**：APP 自动连接到 ESP01
5. **开始监测**：点击"开始监测"按钮
6. **查看数据**：实时显示心率、血氧、波形图

## 性能优化

- **极简协议**：仅传输纯数字，无 HTTP/JSON 开销
- **手机端处理**：95% 计算在手机端完成
- **断线重连**：自动检测连接状态并重连
- **数据缓存**：本地缓存最近 1000 条数据
- **波形优化**：仅保留最近 100 个点绘制

## 故障排查

### 无法连接
- 确认手机已连接到 ESP01 的 WiFi
- 检查 IP 地址是否正确（默认 192.168.4.1）
- 检查端口是否正确（默认 8080）

### 数据不更新
- 检查 ESP01 是否正常发送数据
- 查看 APP 状态是否为"监测中"
- 检查数据格式是否正确

### APP 闪退
- 检查 Python 版本（需要 3.7+）
- 检查 Kivy 是否正确安装
- 查看错误日志

## 技术栈

- **框架**：Kivy 2.0
- **语言**：Python 3
- **打包工具**：Buildozer
- **目标平台**：Android 5.0+ (API 21+)

## 许可证

MIT License