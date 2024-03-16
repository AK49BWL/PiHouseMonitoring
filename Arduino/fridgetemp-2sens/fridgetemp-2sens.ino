#include <Adafruit_AHTX0.h>
Adafruit_AHTX0 aht[2];

void setup() {
  Serial.begin(9600);
  while(!Serial){
    ;
  }
  Serial.setTimeout(2);
  Serial.println(F("[[ fridgetemp-2sens.ino -- 03/16/2024 10:30 ]]"));
  Serial.println(F("Sends data from two AHT21 sensors over serial"));
  if (!aht[0].begin(&Wire,0,0x38) || !aht[1].begin(&Wire,0,0x39)) {
    while(1) {
      Serial.println(F("Sensor init failed"));
      delay(60000);
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
    aht[0].getEvent(&humidity, &temp);
    Serial.print("{ \"T1\": \"");
    Serial.print(temp.temperature * 1.8 + 32, 1);
    Serial.print("\", \"H1\": ");
    Serial.print(humidity.relative_humidity, 0);
    Serial.print(", \"T2\": \"");
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
