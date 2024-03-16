#include <Adafruit_AHTX0.h>
#include <Wire.h>
Adafruit_AHTX0 aht[2];

void setup() {
  Serial.begin(9600);
  while(!Serial){
    ;
  }
  Serial.setTimeout(2);
  Serial.println(F("[[ fridgetemp-mux.ino -- 03/16/2024 10:30 ]]"));
  Serial.println(F("Sends data from two AHT21 sensors via multiplexer over serial"));
  Wire.begin();
  for (byte x = 0; x < 2; x++) {
    mux(x);
    if (! aht[x].begin(&Wire,x,0x38)) {
      while(1) {
        Serial.print(F("Sensor "));
        Serial.print(x);
        Serial.print(F(" init failed"));
        delay(60000);
      }
    }
  }
  Serial.println(F("Send 'S' to read data"));
}
void(* reboot) (void) = 0;

void loop() {
  String comm = Serial.readStringUntil("\n");
  comm.trim();
  if (comm.equals("S")) {
    sensors_event_t humidity, temp;
    mux(0);
    aht[0].getEvent(&humidity, &temp);
    Serial.print("{ \"T1\": \"");
    Serial.print(temp.temperature * 1.8 + 32, 1);
    Serial.print("\", \"H1\": ");
    Serial.print(humidity.relative_humidity, 0);
    Serial.print(", \"T2\": \"");
    mux(1);
    aht[1].getEvent(&humidity, &temp);
    Serial.print(temp.temperature * 1.8 + 32, 1);
    Serial.print("\", \"H2\": ");
    Serial.print(humidity.relative_humidity, 0);
    Serial.println(" }");
    delay(500);
  }
  if (comm.equals("R")) {
    Serial.println(F("Rebooting"));
    delay(1000);
    reboot();
  }
}

void mux(byte c) {
  Wire.beginTransmission(0x70); // 0x70 Default multiplexer ID
  Wire.write(1 << c);
  Wire.endTransmission();
}
