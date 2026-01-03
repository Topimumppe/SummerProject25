# SummerProject25 - RC Car with Raspberry Pi and ESP32 Camera

This project implements a remotely controlled RC car operated through a browser-based web interface. The system provides live video streaming and motor control without requiring an external internet connection. Project is made during Summer 2025 Practical training at Centria university, by **Topi Heikkilä**.

## Hardware

<img src="https://github.com/user-attachments/assets/9ed58a47-0bbe-4d33-b179-c44494f411e3" width="360" height="360">

- Raspberry Pi 3 B  
- L298N motor driver  
- 2 × DC gear motors  
- ESP32S3 Sense camera module  
- 12V AA battery pack (motors)  
- Power bank (Raspberry Pi)  
- Jumper wires  
- Cardboard chassis  

## System Architecture

<img src="https://github.com/user-attachments/assets/1d081b6f-a381-418a-a554-cb7c29696077" width="360" height="360">

- Raspberry Pi acts as:
  - the main control unit for motor logic
  - a Flask-based web server
  - a WiFi hotspot (hostapd + dnsmasq)
- ESP32 camera module:
  - connects to the Raspberry Pi WiFi hotspot
  - serves an MJPEG video stream over HTTP
- User:
  - connects a phone or computer to the Raspberry Pi WiFi network
  - controls the car through a web browser without internet access

## Functionality

### Motor Control
- DC motors are connected to an L298N motor driver
- L298N is interfaced with Raspberry Pi GPIO pins
- Flask web application sends control commands via GPIO
- Motor speed is controlled using PWM signals

<img src="https://github.com/user-attachments/assets/72010156-d299-464d-9eab-ff2876e50a1a" width="360" height="660">

### Web Interface
- Flask-based HTTP server
- Browser-accessible control panel
- Includes:
  - live video feed from the ESP32 camera
  - directional control buttons (forward, backward, left, right)
  - speed control slider

### WiFi Hotspot
- Raspberry Pi is configured as a standalone wireless access point
- Services used:
  - `hostapd` – WiFi access point
  - `dnsmasq` – DHCP server
- Enables usage anywhere without external network infrastructure

### Camera Streaming
- ESP32 runs its own HTTP server
- Camera feed is streamed using MJPEG
- Raspberry Pi fetches and embeds the stream into the web interface
- Entire communication occurs within the local network

## Physical Structure

<img src="https://github.com/user-attachments/assets/afb0c503-bdb3-4b02-bc9f-b63475f9909f" width="360" height="360">

- Chassis built from cardboard
- Bottom:
  - 2 × DC gear motors
  - 1 × free-rotating caster wheel
- Top:
  - Raspberry Pi
  - L298N motor driver
  - ESP32 camera
  - power sources

## Known Limitations

- Noticeable latency in the MJPEG video stream
- Limited WiFi range
- Cardboard chassis is not suitable for long-term use

## Future Improvements

- 3D-printed chassis
- Replace ESP32 camera with Raspberry Pi Camera Module
- Ultrasonic distance sensor for obstacle detection
- External WiFi antenna for improved hotspot performance
- Extended web interface (telemetry, speed data)

## Project Status

The current implementation meets the defined functional requirements and operates as a standalone, browser-controlled RC car with live video feed.

