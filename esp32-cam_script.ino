/*
  HTTP MJPEG streamer for XIAO ESP32S3 Sense
  - Yksinkertainen HTTP-palvelin, joka lähettää MJPEG-videostreamia
  - Käyttää esp32-camera -kirjastoa kuvan kaappaukseen
  - Streami saatavilla osoitteessa http://[IP]/stream
*/

#include <WiFi.h>
#include "esp_camera.h"

// ---------- ASETUKSET ----------
const char* ssid     = "***";
const char* password = "***";

// Camera pins for XIAO ESP32S3 Sense
#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  10
#define SIOD_GPIO_NUM  40
#define SIOC_GPIO_NUM  39
#define Y9_GPIO_NUM    48
#define Y8_GPIO_NUM    11
#define Y7_GPIO_NUM    12
#define Y6_GPIO_NUM    14
#define Y5_GPIO_NUM    16
#define Y4_GPIO_NUM    18
#define Y3_GPIO_NUM    17
#define Y2_GPIO_NUM    15
#define VSYNC_GPIO_NUM 38
#define HREF_GPIO_NUM  47
#define PCLK_GPIO_NUM  13

// Kuvanlaatu
#define FRAME_SIZE      FRAMESIZE_QVGA  // 320x240
const uint8_t  JPEG_QUALITY   = 12;     // 0-63, pienempi = parempi
const uint8_t  FB_COUNT       = 1;      // Framebufferien määrä
const uint16_t TARGET_FPS     = 20;     // Pyritty FPS

// ---------- GLOBALS ----------
WiFiServer server(80);
bool clientConnected = false;

// ---------- KAMERA ----------
void setupCamera() {
  camera_config_t cfg{};
  cfg.ledc_channel = LEDC_CHANNEL_0;
  cfg.ledc_timer   = LEDC_TIMER_0;
  cfg.pin_d0       = Y2_GPIO_NUM;
  cfg.pin_d1       = Y3_GPIO_NUM;
  cfg.pin_d2       = Y4_GPIO_NUM;
  cfg.pin_d3       = Y5_GPIO_NUM;
  cfg.pin_d4       = Y6_GPIO_NUM;
  cfg.pin_d5       = Y7_GPIO_NUM;
  cfg.pin_d6       = Y8_GPIO_NUM;
  cfg.pin_d7       = Y9_GPIO_NUM;
  cfg.pin_xclk     = XCLK_GPIO_NUM;
  cfg.pin_pclk     = PCLK_GPIO_NUM;
  cfg.pin_vsync    = VSYNC_GPIO_NUM;
  cfg.pin_href     = HREF_GPIO_NUM;
  cfg.pin_sccb_sda = SIOD_GPIO_NUM;
  cfg.pin_sccb_scl = SIOC_GPIO_NUM;
  cfg.pin_pwdn     = PWDN_GPIO_NUM;
  cfg.pin_reset    = RESET_GPIO_NUM;
  cfg.xclk_freq_hz = 20000000;
  cfg.pixel_format = PIXFORMAT_JPEG;
  cfg.frame_size   = FRAME_SIZE;
  cfg.jpeg_quality = JPEG_QUALITY;
  cfg.fb_count     = FB_COUNT;

  esp_err_t err = esp_camera_init(&cfg);
  if (err != ESP_OK) {
    Serial.printf("Kamera init epäonnistui: 0x%x\n", err);
    ESP.restart();
  }
}

// ---------- HTTP/MJPEG ----------
void handleMjpegStream(WiFiClient &client) {
  Serial.println("Uusi stream-yhteys");

  // Lähetä HTTP-otsikot
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
  client.println("Connection: close");
  client.println();
  
  uint32_t lastFrameTime = millis();
  uint32_t frameInterval = 1000 / TARGET_FPS;

  while (client.connected()) {
    uint32_t now = millis();
    if (now - lastFrameTime >= frameInterval) {
      lastFrameTime = now;
      
      // Kaappaa kuva
      camera_fb_t *fb = esp_camera_fb_get();
      if (!fb) {
        Serial.println("Kuvan kaappaus epäonnistui");
        continue;
      }

      // Lähetä MJPEG-kehys
      client.println("--frame");
      client.println("Content-Type: image/jpeg");
      client.println("Content-Length: " + String(fb->len));
      client.println();
      client.write(fb->buf, fb->len);
      client.println();

      // Palauta framebuffer
      esp_camera_fb_return(fb);
    }
    
    // Tarkista katkaisiko asiakas yhteyden
    if (!client.connected()) {
      break;
    }
    delay(1);
  }
  
  Serial.println("Stream-yhteys suljettu");
}

void handleHttpRequest(WiFiClient &client) {
  String request = client.readStringUntil('\r');
  client.flush();

  if (request.indexOf("/stream") != -1) {
    handleMjpegStream(client);
  } else {
    // Lähetä yksinkertainen HTML-sivu, jossa on streami
    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: text/html");
    client.println("Connection: close");
    client.println();
    client.println("<!DOCTYPE html><html><head><title>ESP32 Camera</title></head>");
    client.println("<body><h1>ESP32 Camera Stream</h1>");
    client.println("<img src=\"/stream\" width=\"320\" height=\"240\"></body></html>");
  }
}

// ---------- SETUP & LOOP ----------
void setup() {
  Serial.begin(115200);
  Serial.println("\nESP32-S3 Sense MJPEG Streamer");

  // Alusta WiFi
  WiFi.begin(ssid, password);
  Serial.print("Yhdistetään WiFiin");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi yhdistetty");
  Serial.print("IP-osoite: ");
  Serial.println(WiFi.localIP());

  // Alusta kamera
  setupCamera();
  
  // Käynnistä HTTP-palvelin
  server.begin();
  Serial.println("HTTP-palvelin käynnistetty");
  Serial.println("Streami saatavilla osoitteessa:");
  Serial.println("http://" + WiFi.localIP().toString() + "/stream");
}

void loop() {
  WiFiClient client = server.available();
  
  if (client) {
    Serial.println("Uusi asiakas");
    handleHttpRequest(client);
    client.stop();
    Serial.println("Asiakas irti");
  }
  
  delay(10);
}
