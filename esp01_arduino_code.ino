/*
 * ESP01 心率数据发送示例
 * 
 * 功能：接收STM32串口数据，通过WiFi发送给手机APP
 * 协议：极简格式 "心率,血氧,状态\n"
 * 
 * 硬件连接：
 * - STM32 TX -> ESP01 RX (GPIO3)
 * - STM32 RX -> ESP01 TX (GPIO1)
 * - VCC -> 3.3V
 * - GND -> GND
 * - EN -> 3.3V (上拉)
 * - RST -> 3.3V (上拉，可选接按钮复位)
 */

#include <ESP8266WiFi.h>

// WiFi配置（AP模式）
const char* ssid = "HeartRateMonitor";
const char* password = "12345678";

// 服务器配置
WiFiServer server(8080);
WiFiClient client;

// 数据缓冲
String inputBuffer = "";
unsigned long lastDataTime = 0;
const unsigned long timeoutMs = 5000; // 5秒无数据断开

// LED指示灯（可选）
const int ledPin = 2; // ESP01的GPIO2，板载LED

void setup() {
  // 初始化串口（与STM32通信）
  Serial.begin(115200);
  
  // 初始化LED
  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, HIGH); // 熄灭
  
  // 配置为AP模式
  WiFi.mode(WIFI_AP);
  WiFi.softAP(ssid, password);
  
  // 启动服务器
  server.begin();
  server.setNoDelay(true);
  
  // 输出调试信息
  Serial.println();
  Serial.println("=================================");
  Serial.println("ESP01 Heart Rate Monitor");
  Serial.println("=================================");
  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());
  Serial.print("Port: ");
  Serial.println(8080);
  Serial.println("Waiting for client...");
  
  // LED闪烁表示启动完成
  for (int i = 0; i < 3; i++) {
    digitalWrite(ledPin, LOW);
    delay(100);
    digitalWrite(ledPin, HIGH);
    delay(100);
  }
}

void loop() {
  // 检查新客户端连接
  if (server.hasClient()) {
    if (client && client.connected()) {
      // 已有客户端连接，拒绝新连接
      WiFiClient newClient = server.available();
      newClient.stop();
    } else {
      // 接受新连接
      client = server.available();
      client.setNoDelay(true);
      lastDataTime = millis();
      Serial.println("Client connected!");
      digitalWrite(ledPin, LOW); // 点亮LED
    }
  }
  
  // 检查客户端连接状态
  if (client && client.connected()) {
    // 检查超时
    if (millis() - lastDataTime > timeoutMs) {
      Serial.println("Timeout, disconnecting...");
      client.stop();
      digitalWrite(ledPin, HIGH); // 熄灭LED
    }
    
    // 从STM32读取数据并转发
    while (Serial.available()) {
      char c = Serial.read();
      inputBuffer += c;
      
      // 检测到换行符，发送完整数据包
      if (c == '\n') {
        // 发送到手机
        client.print(inputBuffer);
        
        // 调试输出
        Serial.print("Sent: ");
        Serial.print(inputBuffer);
        
        // 清空缓冲
        inputBuffer = "";
        lastDataTime = millis();
        
        // LED闪烁
        digitalWrite(ledPin, HIGH);
        delay(10);
        digitalWrite(ledPin, LOW);
      }
    }
    
    // 缓冲区保护（防止数据堆积）
    if (inputBuffer.length() > 100) {
      inputBuffer = "";
    }
  } else {
    // 无客户端连接时，清空串口缓冲
    while (Serial.available()) {
      Serial.read();
    }
    inputBuffer = "";
  }
  
  delay(1); // 防止看门狗复位
}

/*
 * STM32端发送示例代码：
 * 
 * // STM32通过串口发送数据给ESP01
 * void sendHeartRateData(int heartRate, int spo2, int status) {
 *     Serial1.print(heartRate);
 *     Serial1.print(",");
 *     Serial1.print(spo2);
 *     Serial1.print(",");
 *     Serial1.println(status);
 * }
 * 
 * // 示例调用
 * sendHeartRateData(78, 95, 0);  // 正常
 * sendHeartRateData(120, 88, 1); // 注意
 * sendHeartRateData(45, 92, 2);  // 警告
 */

/*
 * 数据格式说明：
 * 
 * 格式：心率,血氧,状态\n
 * 
 * 心率：40-200 (BPM)
 * 血氧：70-100 (%)
 * 状态：
 *   0 - 正常
 *   1 - 注意（轻微异常）
 *   2 - 警告（严重异常）
 * 
 * 示例：
 *   78,95,0   -> 心率78，血氧95%，正常
 *   120,88,1  -> 心率120，血氧88%，注意
 *   45,92,2   -> 心率45，血氧92%，警告
 */

/*
 * 性能优化建议：
 * 
 * 1. 波特率：使用115200或更高，确保数据传输速度
 * 2. 数据频率：建议每秒发送1-2次，避免数据堆积
 * 3. 连接数：仅支持单客户端连接，减少资源占用
 * 4. 超时处理：5秒无数据自动断开，释放资源
 * 5. LED指示：连接时点亮，数据传输时闪烁
 */