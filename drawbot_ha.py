from ha_mqtt_discoverable import Settings, DeviceInfo
from ha_mqtt_discoverable.sensors import BinarySensor, BinarySensorInfo, Button, ButtonInfo, Sensor, SensorInfo, Text, TextInfo, Image, ImageInfo
import os
from typing import Callable
from datetime import datetime, timedelta
from drawbot_control import DrawbotControl
import socket
import logging
from flask import url_for
#logging.basicConfig(level=logging.DEBUG)

class HAConnection:
    def __init__(self,drawbot_control:DrawbotControl,config_url:str,mqtt_host="moominpappa.local",image_path:str=None,no_drawing_image_path:str='static/no_drawing.svg'):
        self.image_path = image_path
        self.drawbot_control = drawbot_control
        drawbot_control.add_state_listener(self)
        print("Connecting to MQTT / HA")
        self.mqtt_settings = Settings.MQTT(host=mqtt_host)
        print(self.mqtt_settings)
        self.fake = 'FAKE_DRAWBOT' in os.environ
        print("Setting up device info")
        drawbot_type="Fake" if self.fake else "Real"
        drawbot_manufacturer="Dave" if self.fake else "Matt Venn"
        hostname=socket.gethostname()
        uid=f"{drawbot_type}_{hostname}".replace("\\s","_")
        self.image_url = f"{config_url}/{image_path}"
        self.no_drawing_image_url = f"{config_url}/{no_drawing_image_path}"
        self.uid = uid
        self.device_info = DeviceInfo(
            name=f"Drawbot {hostname} {drawbot_type}",
            model=drawbot_type,
            identifiers=f"Polarbot_{uid}",
            unique_id=uid,
            manufacturer=drawbot_manufacturer,
            #configuration_url=config_url
            configuration_url=self.image_url
        )
        print("HA Device Info:\n----------")
        print(self.device_info)
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
            unique_id=f"drawbot_progress_{uid}",
            icon="mdi:progress-wrench",
            device=self.device_info,
            unit_of_measurement="%",
        )
        self.progress_sensor = Sensor(Settings(mqtt=self.mqtt_settings,entity=self.progress_sensor_info))
        self.progress_sensor.set_state(0)

        print("Adding progress amount sensor")
        self.progress_amount_sensor_info = TextInfo(
            name="Progress Amount",
            unique_id=f"drawbot_progress_amount_{uid}",
            icon="mdi:progress-wrench",
            device=self.device_info,
        )
        self.progress_amount_sensor = Text(Settings(mqtt=self.mqtt_settings,entity=self.progress_amount_sensor_info),self.null_callback)
        self.progress_amount_sensor.set_text("0/0")




        print("Adding current state text")
        self.current_state_text_info = TextInfo(
            name="Current State",
            unique_id=f"drawbot_current_state_{uid}",
            icon="mdi:home",
            device=self.device_info,
        )
        self.current_state_text = Text(Settings(mqtt=self.mqtt_settings,entity=self.current_state_text_info),self.null_callback)
        self.current_state_text.set_text("idle")

        print("Adding end time text")
        self.end_time_text_info = TextInfo(
            name="End Time",
            unique_id=f"drawbot_end_time_{uid}",
            icon="mdi:clock",
            device=self.device_info,
        )
        self.end_time_text = Text(Settings(mqtt=self.mqtt_settings,entity=self.end_time_text_info),self.null_callback)
        self.end_time_text.set_text("N/A")

        print("Adding image sensor")
        self.image_sensor_info = ImageInfo(
            name="Current Drawing",
            unique_id=f"drawbot_image_{uid}",
            icon="mdi:image",
            device=self.device_info,
            url_topic=f"hmd/image/{uid}/Image/state",
        )
        self.image_sensor = Image(Settings(mqtt=self.mqtt_settings,entity=self.image_sensor_info))
        self.image_sensor.set_url(self.image_url)

        print("Adding Target Image sensor")
        self.target_image_sensor_info = ImageInfo(
            name="Target Drawing",
            unique_id=f"drawbot_target_image_{uid}",
            icon="mdi:image",
            device=self.device_info,
            url_topic=f"hmd/image/{uid}_target/Image/state",
        )
        self.target_image_sensor = Image(Settings(mqtt=self.mqtt_settings,entity=self.target_image_sensor_info))
        self.target_image_sensor.set_url(self.no_drawing_image_url)

        print("Adding config URL Entity")
        self.config_url_entity_info = TextInfo(
            name="Config URL",
            unique_id=f"drawbot_config_url_{uid}",
            icon="mdi:clock",
            device=self.device_info,
        )
        self.config_url_entity = Text(Settings(mqtt=self.mqtt_settings,entity=self.config_url_entity_info),self.null_callback)
        self.config_url_entity.set_text(config_url)
        
        print("Finished setting up HA")

    def set_state(self,state:str):
        try:    
            self.current_state_text.set_text(state)
        except Exception as e:
            print(f"Error setting state: {e}")

    def set_progress(self,progress:float,done:int,total:int):
        try:
            self.progress_sensor.set_state(progress)
            self.progress_amount_sensor.set_text(f"{done}/{total}")
            self.image_sensor.set_url(self.image_url)
        except Exception as e:
            print(f"Error setting progress: {e}")

    def set_config_url(self,config_url:str):
        try:
            self.config_url_entity.set_text(config_url)
        except Exception as e:
            print(f"Error setting config URL: {e}")

    def set_target_image(self,image_path:str=None):
        try:
            if image_path:
                self.target_image_sensor.set_url(image_path)
            else:
                self.target_image_sensor.set_url(self.no_drawing_image_url)
        except Exception as e:
            print(f"Error setting target image: {e}")

    def set_estimated_time_left(self,time_left:float):
        try:
            if time_left:
                if time_left < 0:
                    self.end_time_text.set_text("Done")
                else:
                    end_date = datetime.now() + timedelta(seconds=time_left)
                    self.end_time_text.set_text(end_date.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                self.end_time_text.set_text("N/A")
        except Exception as e:
            print(f"Error setting estimated end time: {e}")

    def add_button(self,name:str,icon:str,callback:Callable):
        print(f"Adding button {name}")
        button_info = ButtonInfo(
            name=name,
            unique_id=f"drawbot_{name}_{self.uid}",
            icon=icon,
            device=self.device_info,
        )
        button_settings = Settings(mqtt=self.mqtt_settings,entity=button_info)
        button = Button(button_settings, lambda client,user_data,message: callback())
        button.write_config()