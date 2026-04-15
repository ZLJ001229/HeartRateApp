/*
 * ESP01 (ESP8266) 固件 - 心率监测专用
 * 
 * 硬件连接：
 *   STM32H7 PA10 (TX) → ESP01 RX (GPIO3)
 *   STM32H7 PA9  (RX) → ESP01 TX (GPIO1)
 *   3.3V → VCC, EN(CH_PD)
 *   GND  → GND
 * 
 * 功能：
 *   1. 创建WiFi热点 "HeartRateMonitor"
 *   2. 启动TCP服务器 (端口8080)
 *   3. 接收STM32串口数据，转发给手机APP
 * 
 * 协议：心率,评分,状态\n
 *   例: 78,95,0
 */

#include <ESP8266WiFi.h>

const char* ssid     = "HeartRateMonitor";
const char* password = "12345678";

WiFiServer tcpServer(8080);
WiFiClient activeClient;

#define LED_PIN 2  // ESP01板载LED (GPIO2)

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH); // 熄灭

  // 串口与STM32通信
  Serial.begin(115200);
  delay(500);
  Serial.println(); // 空行，帮助STM32识别ESP01就绪

  // WiFi AP模式
  WiFi.mode(WIFI_AP);
  WiFi.softAP(ssid, password);
  
  // 启动TCP服务器
  tcpServer.begin();
  tcpServer.setNoDelay(true);

  // LED快闪3次表示启动完成
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, LOW); delay(80);
    digitalWrite(LED_PIN, HIGH); delay(80);
  }
}

void loop() {
  // 检查新客户端连接
  if (tcpServer.hasClient()) {
    if (!activeClient || !activeClient.connected()) {
      activeClient = tcpServer.available();
      activeClient.setNoDelay(true);
      digitalWrite(LED_PIN, LOW); // 连接时点亮LED
    } else {
      // 已有客户端，拒绝新连接
      WiFiClient rejected = tcpServer.available();
      rejected.stop();
    }
  }

  // 检查客户端是否断开
  if (activeClient && !activeClient.connected()) {
    activeClient.stop();
    digitalWrite(LED_PIN, HIGH); // 断开时熄灭LED
  }

  // 从STM32读取数据，转发给手机
  if (activeClient && activeClient.connected()) {
    while (Serial.available()) {
      char c = Serial.read();
      activeClient.write(c); // 逐字节转发，最高效
      
      // LED闪烁指示数据传输
      if (c == '\n') {
        digitalWrite(LED_PIN, HIGH);
        delay(5);
        digitalWrite(LED_PIN, LOW);
      }
    }
  } else {
    // 无客户端时，清空串口缓冲
    while (Serial.available()) Serial.read();
  }

  delay(1); // 防止看门狗
}