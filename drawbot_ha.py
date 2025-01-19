from ha_mqtt_discoverable import Settings, DeviceInfo
from ha_mqtt_discoverable.sensors import BinarySensor, BinarySensorInfo, Button, ButtonInfo, Sensor, SensorInfo, Text, TextInfo, Image, ImageInfo
import os
from typing import Callable
from datetime import datetime
from drawbot_control import DrawbotControl

import logging
#logging.basicConfig(level=logging.DEBUG)

class HAConnection:
    def __init__(self,drawbot_control:DrawbotControl,mqtt_host="moominpappa.local",):
        self.drawbot_control = drawbot_control
        drawbot_control.add_state_listener(self)
        print("Connecting to MQTT / HA")
        self.mqtt_settings = Settings.MQTT(host=mqtt_host)
        print(self.mqtt_settings)
        self.fake = 'FAKE_DRAWBOT' in os.environ
        print("Setting up device info")
        self.device_info = DeviceInfo(
            name="Drawbot",
            model="fake" if self.fake else "real",
            identifiers="drawbot",
            manufacturer="mattyboombatty"
        )
        self.null_callback = lambda a, b, c: print(f"Got text message {a} {b} {c}")
        #self.mqtt_settings.add_device(self.device_info)
        print("Adding buttons")
        self.add_button("Calibrate","mdi:calibrate",lambda: self.drawbot_control.calibrate())   
        self.add_button("Home","mdi:home",lambda: self.drawbot_control.home())   
        self.add_button("Pen Up","mdi:pencil",lambda: self.drawbot_control.pen_up())   
        self.add_button("Pen Down","mdi:pencil",lambda: self.drawbot_control.pen_down())   

        print("Adding progress sensor")
        self.progress_sensor_info = SensorInfo(
            name="Progress",
            unique_id="drawbot_progress",
            icon="mdi:progress-wrench",
            device=self.device_info,
            unit_of_measurement="%",
        )
        self.progress_sensor = Sensor(Settings(mqtt=self.mqtt_settings,entity=self.progress_sensor_info))
        self.progress_sensor.set_state(0)

        print("Adding current state text")
        self.current_state_text_info = TextInfo(
            name="Current State",
            unique_id="drawbot_current_state",
            icon="mdi:home",
            device=self.device_info,
        )
        self.current_state_text = Text(Settings(mqtt=self.mqtt_settings,entity=self.current_state_text_info),self.null_callback)
        self.current_state_text.set_text("idle")

        print("Adding end time text")
        self.end_time_text_info = TextInfo(
            name="End Time",
            unique_id="drawbot_end_time",
            icon="mdi:clock",
            device=self.device_info,
        )
        self.end_time_text = Text(Settings(mqtt=self.mqtt_settings,entity=self.end_time_text_info),self.null_callback)
        self.end_time_text.set_text("N/A")

        print("Adding image sensor")
        self.image_sensor_info = ImageInfo(
            name="Image",
            unique_id="drawbot_image",
            icon="mdi:image",
            device=self.device_info,
        )
        self.image_sensor = Image(Settings(mqtt=self.mqtt_settings,entity=self.image_sensor_info),self.null_callback)
        self.image_sensor.set_url("https://www.google.com/images/branding/googlelogo/2x/googlelogo_light_color_272x92dp.png")
        print("Finished setting up HA")

    def set_state(self,state:str):
        self.current_state_text.set_text(state)

    def set_progress(self,progress:float):
        self.progress_sensor.set_state(progress)

    def set_image_url(self,image_url:str):
        print(f"Setting image URL for HA: {image_url}")
        self.image_sensor.set_url(image_url)

    def set_estimated_end_time(self,end_time:datetime):
        if end_time:
            self.end_time_text.set_text(end_time.strftime('%Y-%m-%d %H:%M:%S'))
        else:
            self.end_time_text.set_text("N/A")

    def add_button(self,name:str,icon:str,callback:Callable):
        print(f"Adding button {name}")
        button_info = ButtonInfo(
            name=name,
            unique_id=f"drawbot_{name}",
            icon=icon,
            device=self.device_info,
        )
        button_settings = Settings(mqtt=self.mqtt_settings,entity=button_info)
        button = Button(button_settings, lambda client,user_data,message: callback())
        button.write_config()