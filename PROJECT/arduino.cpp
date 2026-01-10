#include <ESP32Servo.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// =========================================================
// 1. WIFI & MQTT CONFIGURATION
// =========================================================
const char *WIFI_SSID = "izzatiayb";
const char *WIFI_PASSWORD = "izzati1234";

const char *MQTT_SERVER = "136.111.56.9";
const char *MQTT_TOPIC = "iot";
const int MQTT_PORT = 1883;

WiFiClient espClient;
PubSubClient client(espClient);

// =========================================================
// 2. PIN DEFINITIONS
// =========================================================
const int ldrPin = A4;
const int pirPin = 5;

// --- BREADBOARD SENSORS ---
const int mq2Pin = A1;
const int mq135Pin = A2;
const int rainPin = 10;

// --- ACTUATORS ---
const int fanRelayPin = 14;
const int ledRelayPin = 47;
const int servoPin = 21;
const int buzzerPin = 12;

// --- SECURITY ---
const int panicButtonPin = 48;

// =========================================================
// 3. SETTINGS & VARIABLES
// =========================================================
const int smokeThreshold = 4000;
const int airQualityThreshold = 4000;
const int lightThreshold = 1500;

const bool TEST_MODE = false;

Servo windowServo;
volatile bool motionDetected = false;
bool isSystemActive = false;
unsigned long lastMotionTime = 0;
const int activeDuration = 2000;

bool isWindowClosed = false;
int windowOpenAngle = 0;
int windowClosedAngle = 100;

// --- EMERGENCY ---
bool emergencyActive = false;
unsigned long emergencyStartTime = 0;
const unsigned long emergencyDuration = 15000;

// --- SENSOR WARMUP ---
unsigned long startupTime = 0;
const unsigned long sensorWarmupTime = 30000;

// MQTT Timer
unsigned long lastMsgTime = 0;
const long interval = 5000;

// =========================================================
// 4. HELPER FUNCTIONS
// =========================================================

// *** WIFI SETUP ***
void setup_wifi()
{
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  // Try to connect for 10 seconds (20 * 500ms)
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20)
  {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("\n✅ WiFi connected");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
  }
  else
  {
    Serial.println("\n⚠️ WiFi Failed! Continuing offline...");
  }
}

void reconnect()
{
  // Only try to reconnect if WiFi is actually connected
  if (WiFi.status() != WL_CONNECTED)
    return;

  if (!client.connected())
  {
    Serial.print("Connecting to MQTT...");
    if (client.connect("ESP32_IoT_Client"))
    {
      Serial.println("✅ Connected to MQTT");
    }
    else
    {
      Serial.print("❌ Failed, rc=");
      Serial.println(client.state());
    }
  }
}

void playTone(int pin, int frequency, int duration)
{
  long delayAmount = 1000000 / frequency / 2;
  long loops = frequency * duration / 1000;
  for (long i = 0; i < loops; i++)
  {
    digitalWrite(pin, HIGH);
    delayMicroseconds(delayAmount);
    digitalWrite(pin, LOW);
    delayMicroseconds(delayAmount);
  }
}

void IRAM_ATTR motionDetect()
{
  motionDetected = true;
}

void triggerEmergency()
{
  emergencyActive = true;
  emergencyStartTime = millis();

  Serial.println("🚨 EMERGENCY MODE ACTIVATED");

  windowServo.write(windowClosedAngle);
  isWindowClosed = true;

  playTone(buzzerPin, 1200, 500);
}

// =========================================================
// 5. SETUP
// =========================================================
void setup()
{
  // *** SAFETY DELAY ***
  delay(5000);

  Serial.begin(115200);
  Serial.println("\n=== ESP32 SYSTEM STARTED ===");

  startupTime = millis();

  pinMode(pirPin, INPUT);
  pinMode(rainPin, INPUT);
  pinMode(mq2Pin, INPUT);
  pinMode(mq135Pin, INPUT);
  pinMode(ldrPin, INPUT);

  pinMode(fanRelayPin, OUTPUT);
  pinMode(ledRelayPin, OUTPUT);
  pinMode(buzzerPin, OUTPUT);
  pinMode(panicButtonPin, INPUT_PULLUP);

  digitalWrite(buzzerPin, LOW);
  digitalWrite(fanRelayPin, HIGH);
  digitalWrite(ledRelayPin, HIGH);

  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  windowServo.setPeriodHertz(50);
  windowServo.attach(servoPin, 500, 2400);
  windowServo.write(windowOpenAngle);

  attachInterrupt(digitalPinToInterrupt(pirPin), motionDetect, RISING);

  setup_wifi();
  client.setServer(MQTT_SERVER, MQTT_PORT);
}

// =========================================================
// 6. MAIN LOOP
// =========================================================
void loop()
{
  // Ensure we only try MQTT if WiFi is alive
  if (WiFi.status() == WL_CONNECTED)
  {
    if (!client.connected())
    {
      // Simple non-blocking reconnect check could go here
      reconnect();
    }
    client.loop();
  }

  // ---------- PANIC BUTTON ----------
  if (digitalRead(panicButtonPin) == LOW && !emergencyActive)
  {
    delay(50);
    if (digitalRead(panicButtonPin) == LOW)
    {
      Serial.println("🛑 Panic button pressed");
      triggerEmergency();
    }
  }

  // ---------- SENSOR READ ----------
  int smokeValue = analogRead(mq2Pin);
  int airValue = analogRead(mq135Pin);
  int lightLevel = analogRead(ldrPin);
  bool rainDetected = (digitalRead(rainPin) == LOW);

  // ---------- DEBUG SENSOR VALUES ----------
  //
  static unsigned long lastDebug = 0;
  if (millis() - lastDebug > 2000)
  {
    Serial.print("Smoke: ");
    Serial.print(smokeValue);
    Serial.print(" | Air: ");
    Serial.print(airValue);
    Serial.print(" | Rain: ");
    Serial.print(rainDetected);
    Serial.print(" | PanicBtn: ");
    Serial.println(digitalRead(panicButtonPin));
    lastDebug = millis();
  }

  // ---------- SMOKE ALARM ----------
  if (millis() - startupTime > sensorWarmupTime)
  {
    bool smokeAlarm = smokeValue > smokeThreshold;
    if (smokeAlarm)
    {
      Serial.println("🔥 Smoke threshold exceeded!");
      playTone(buzzerPin, 1000, 100);
    }
  }

  // ---------- WINDOW CONTROL ----------
  bool badAir = airValue > airQualityThreshold;

  if (rainDetected || badAir || emergencyActive)
  {
    if (!isWindowClosed)
    {
      Serial.println("🔒 Closing window");
      windowServo.write(windowClosedAngle);
      isWindowClosed = true;
    }
  }
  else
  {
    if (isWindowClosed)
    {
      Serial.println("🔓 Opening window");
      windowServo.write(windowOpenAngle);
      isWindowClosed = false;
    }
  }

  // ---------- SMART COMFORT ----------
  bool isDark = (lightLevel > lightThreshold);

  if (motionDetected && !emergencyActive)
  {
    Serial.println("👣 Motion detected");
    digitalWrite(fanRelayPin, LOW);
    digitalWrite(ledRelayPin, isDark ? LOW : HIGH);
    isSystemActive = true;
    lastMotionTime = millis();
    motionDetected = false;
  }

  if (isSystemActive && millis() - lastMotionTime > activeDuration)
  {
    Serial.println("💤 No motion, system idle");
    digitalWrite(fanRelayPin, HIGH);
    digitalWrite(ledRelayPin, HIGH);
    isSystemActive = false;
  }

  // ---------- EMERGENCY MODE ----------
  if (emergencyActive)
  {
    digitalWrite(ledRelayPin, LOW);
    playTone(buzzerPin, 1000, 100);
    delay(200);
    digitalWrite(ledRelayPin, HIGH);
    delay(200);

    if (millis() - emergencyStartTime > emergencyDuration)
    {
      emergencyActive = false;
      Serial.println("✅ Emergency ended");
    }
  }

  // ---------- MQTT ----------
  if (millis() - lastMsgTime > interval)
  {
    lastMsgTime = millis();

    StaticJsonDocument<256> doc;
    doc["smoke"] = smokeValue;
    doc["air"] = airValue;
    doc["light"] = lightLevel;
    doc["rain"] = rainDetected;
    doc["motion"] = isSystemActive;
    doc["window"] = isWindowClosed ? "CLOSED" : "OPEN";
    doc["emergency"] = emergencyActive ? "true" : "false";

    char buffer[512];
    serializeJson(doc, buffer);

    if (client.connected())
    {
      Serial.print("📡 MQTT Publish: ");
      Serial.println(buffer);
      client.publish(MQTT_TOPIC, buffer);
    }
  }
  // Removed delay(1000) to keep loop responsive
  // Using small delay for stability
  delay(100);
}