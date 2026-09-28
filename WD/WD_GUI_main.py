# ============================================================
# WD_GUI_main.py
# ============================================================
#
# ไฟล์หลักของโปรแกรม GUI (PySide6) สำหรับตั้งค่า/สร้างสัญญาณแล้วส่งไปบอร์ด Redpitaya
#
# โครงสร้างแบ่งเป็น 2 ชั้น
#   ชั้นข้อมูล : Pin, StepBlock, SignalProfile, SignalProperties, DataManager
#               (เก็บ state + สร้างข้อมูลสัญญาณเป็น numpy array)
#   ชั้น GUI  : MainDialog (หน้าหลัก), CombinePlotDialog, SetupPopup
#
# flow คร่าว ๆ:
#   ผู้ใช้กรอกค่าบน GUI -> DataManager เก็บ/สร้างสัญญาณ -> กด Run
#   -> get_all_pin_data_for_send() แปลงเป็น JSON -> WD_command_send ส่งไปบอร์ด
# ============================================================

# ------------------------------------------------------------
# วิธีเพิ่ม Signal Profile ใหม่ (เช่น analog "Sine"):
#   1. เพิ่มสมาชิกใน SignalTypeAnalog / SignalTypeDigital
#      (ค่า string ต้องตรงกับข้อความใน comboBox )
#   2. เพิ่ม item ใน comboBox (ไฟล์ WD_GUI / WD_Setup)
#   3. เขียนเมธอด _gen_xxx() ใน SignalProperties + ต่อ elif
#      ใน gen_signal_data() (ตรง comment "เพิ่มการสร้างสัญญาญ...")
#   4. เพิ่ม branch log ใน MainDialog.update_signal_properties()
#   ถ้ามีพารามิเตอร์ใหม่: แก้ SignalProfile.__init__ / set_default /
#   clone() ด้วย + เพิ่มหน้าใน SetupPopup (_update_page / accept / _save_xxx)
# ------------------------------------------------------------

from enum import Enum
import numpy as np

from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel, QScrollArea, QWidget,
)
from PySide6.QtCore import QTimer

from WD_GUI import Ui_Dialog
from WD_Setup import Ui_Dialog as SetupSignal
import pyqtgraph as pg
from WD_command_send import connect_board, disconnect_board, poweroff_board, run_signal_gen_wd, stop_signal_gen_wd, check_connection_status

from datetime import datetime

# ============================================================
# Enums
# ============================================================
# ชนิดของขา I/O
class PinType(Enum):
    ANALOG      = "Analog"
    DIGITAL_N   = "Digital_N"
    DIGITAL_P   = "Digital_P"


# รูปแบบสัญญาณที่ขา analog รองรับ
class SignalTypeAnalog(Enum):
    CONSTANT    = "Constant"
    LINEAR_UP   = "Linear_Up"
    LINEAR_DOWN = "Linear_Down"


# รูปแบบสัญญาณที่ขา digital รองรับ
class SignalTypeDigital(Enum):
    LOW     = "Low"
    HIGH    = "High"


# ============================================================
# Pin
# ============================================================
class Pin:
    '''
    แทนขา I/O 1 ขา เก็บชื่อ / ชนิด / index และสถานะว่าเปิดใช้งานอยู่ไหม
    '''
    def __init__(self, pin_name):
        self._pin_name = pin_name.upper()

        # แกะชนิดขาจาก prefix ของชื่อ: ขึ้นต้น "A" = analog, "D" = digital (ต้องลงท้าย _N / _P)
        # pin_type
        if self._pin_name.startswith("A"):
            self._pin_type = PinType.ANALOG
        elif self._pin_name.startswith("D"):
            if self._pin_name.endswith("_N"):
                self._pin_type = PinType.DIGITAL_N
            elif self._pin_name.endswith("_P"):
                self._pin_type = PinType.DIGITAL_P
            else:
                raise ValueError(f"Invalid Digital Pin_Name: {self._pin_name}")
        else:
            raise ValueError(f"Invalid pin name: {pin_name}")

        # ดึงเลข index จากส่วนกลางของชื่อ เช่น "AOUT_2" -> 2, "D_5_N" -> 5
        # pin_index
        parts = self._pin_name.split("_")
        self._pin_index = int(parts[1])

        # enabled
        self.enabled = False

    # =========================
    # Read-only properties
    # =========================
    @property
    def pin_name(self):
        return self._pin_name

    @property
    def pin_index(self):
        return self._pin_index

    @property
    def pin_type(self):
        return self._pin_type

    # =========================
    # Methods
    # =========================
    def disable(self):
        self.enabled = False

    def enable(self):
        self.enabled = True

    def reset(self):
        self.disable()

    def is_analog(self):
        return self.pin_type == PinType.ANALOG

    def is_digital(self):
        return self.pin_type in (PinType.DIGITAL_N, PinType.DIGITAL_P)

    def __repr__(self):
        return (f"Name -> {self.pin_name}\n"
                f"Index -> {self.pin_index}\n"
                f"Enabled: {self.enabled}\n"
                f"Type -> {self.pin_type.value}")


# ============================================================
# StepBlock
# ============================================================
class StepBlock:
    '''
    แทน 1 step ของ sequence เก็บชื่อ step กับระยะเวลา (หน่วยวินาที)
    '''
    def __init__(self, step_number):
        self._step_number = step_number
        self.step_name = ""
        self.duration = 0

    # ============================
    # Read-only property
    # ============================
    @property
    def step_number(self):
        return self._step_number

    @property
    def is_empty(self):
        # ใช้เช็คว่า step นี้ยังไม่ถูกตั้งค่าอะไรเลย
        return self.step_name == "" and self.duration == 0

    # =============================
    # duration properties
    # =============================
    @property
    def duration(self):
        return self._duration

    @duration.setter
    def duration(self, value):
        # กันไม่ให้ใส่ string หรือค่าติดลบ และเก็บเป็น float เสมอ
        if isinstance(value, str):
            raise ValueError("Duration must be int or float")
        if value < 0:
            raise ValueError("Duration must be >= 0")
        self._duration = float(value)

    # =============================
    # Methods
    # =============================
    def reset(self):
        self.step_name = ""
        self.duration = 0

    def __repr__(self):
        return (f"Step -> {self.step_number}\n"
                f"Step name -> {self.step_name}\n"
                f"Duration -> {self.duration}\n"
                )


# ============================================================
# SignalProfile
# ============================================================
class SignalProfile:
    '''
    เก็บ "รูปแบบสัญญาณ + พารามิเตอร์" ของขา 1 ขา
    (signal_type, amplitude, offset, min_amp, max_amp) โดยค่า default
    ต่างกันตามชนิดขา analog / digital
    '''
    def __init__(self, pin_type):
        self._pin_type = pin_type

        self.signal_type = None

        self.amplitude   = 0
        self.offset      = 0

        self.min_amp     = 0
        self.max_amp     = 0

        self.set_default()

    # ===================================
    # Read-only
    # ===================================
    @property
    def pin_type(self):
        return self._pin_type

    # ===================================
    # Methods
    # ===================================
    def set_default(self):
        if self._pin_type == PinType.ANALOG:
            self.signal_type = SignalTypeAnalog.CONSTANT
            self.amplitude   = 0
            self.offset      = 0
            self.min_amp     = 0
            self.max_amp     = 0 

        # digital ใช้แค่ระดับ HIGH/LOW: default HIGH = 3.3V, LOW = 0V
        # offset / max_amp ตั้งเป็น None เพราะไม่ได้ใช้กับ digital
        elif self._pin_type in (PinType.DIGITAL_N, PinType.DIGITAL_P):

            self.signal_type = SignalTypeDigital.LOW
            self.amplitude   = 3.3
            self.offset      = None
            self.min_amp     = 0
            self.max_amp     = None

        else:
            raise TypeError(f"Unsupported pin type: {self._pin_type}")

    def set_signal_type(self, signal_type):
        # กันไม่ให้ยัด signal type ผิดชนิดขา (analog ต้องเป็น SignalTypeAnalog เท่านั้น ฯลฯ)
        if self._pin_type == PinType.ANALOG:
            if not isinstance(signal_type, SignalTypeAnalog):
                raise TypeError("Invalid Analog Signal Type")

        elif self._pin_type in (PinType.DIGITAL_N, PinType.DIGITAL_P):
            if not isinstance(signal_type, SignalTypeDigital):
                raise TypeError("Invalid Digital Signal Type")

        self.signal_type = signal_type 

    def clone(self):
        # ก๊อป profile ออกไปให้ popup แก้ โดยไม่กระทบตัวจริงจนกว่าจะกด update signal
        new_profile = SignalProfile(self.pin_type)

        new_profile.signal_type = self.signal_type
        new_profile.amplitude   = self.amplitude
        new_profile.offset      = self.offset
        new_profile.min_amp     = self.min_amp    
        new_profile.max_amp     = self.max_amp    

        return new_profile

    def __repr__(self):
        return (f"SignalProfile: type -> {self.signal_type.value}\n"
                f"Amplitude -> {self.amplitude}\n"
                f"Offset -> {self.offset}\n"
                f"Min Amp -> {self.min_amp}\n"
                f"Max Amp -> {self.max_amp}\n"
                )


# ============================================================
# SignalProperties
# ============================================================
class SignalProperties:
    '''
    ข้อมูลสัญญาณของ "1 ขา ใน 1 step" = ผูก Pin + SignalProfile + ชื่อสัญญาณ
    เข้าด้วยกัน และเก็บผล gen เป็น numpy array ไว้ที่ _pin_step_data
    '''
    def __init__(self, pin):
        self._pin = pin
        self.signal_name = ""
        self._signal_profile = SignalProfile(self._pin.pin_type)

        self._pin_step_data = np.array([])   # ข้อมูลสัญญาณหลัง gen (ว่างจนกว่าจะเรียก gen_signal_data)

    # =============================================
    # Read-only properties
    # =============================================
    @property
    def pin(self):
        return self._pin

    @property
    def signal_profile(self):
        return self._signal_profile

    @signal_profile.setter 
    def signal_profile(self, value):
        if not isinstance(value, SignalProfile):
            raise TypeError("signal_profile must be a SignalProfile instance")
        self._signal_profile = value

    # @property
    # def sample_count(self):
    #     return len(self._pin_step_data)

    # @property
    # def is_empty(self):
    #     return self.sample_count == 0

    @property
    def pin_step_data(self):
        return self._pin_step_data

    # ===============================================
    # Methods
    # ===============================================
    def gen_signal_data(self, duration, dt):
        '''
        สร้างข้อมูลสัญญาณเก็บลง _pin_step_data

        จำนวน sample = duration / dt แล้ว dispatch ไปฟังก์ชัน _gen_* ตาม signal_type
        '''
        # self.validate()
        sample_count = int(duration / dt)
        profile = self._signal_profile
        
        # ถ้าจะเพิ่มการสร้างสัญญาญรูปแบบอื่นตรงนี้
        if profile.signal_type == SignalTypeAnalog.CONSTANT:
            self._gen_constant(sample_count)
        elif profile.signal_type == SignalTypeAnalog.LINEAR_UP:
            self._gen_linear_up(sample_count)

        elif profile.signal_type == SignalTypeAnalog.LINEAR_DOWN:
            self._gen_linear_down(sample_count)

        elif profile.signal_type == SignalTypeDigital.LOW:
            self._gen_digital_low(sample_count)

        elif profile.signal_type == SignalTypeDigital.HIGH:
            self._gen_digital_high(sample_count)

        else:
            raise TypeError(f"Unsupported signal type: {profile.signal_type}")

    def _gen_constant(self, sample_count):
        '''สร้างสัญญาณคงที่: amplitude + offset'''
        value = self._signal_profile.amplitude + self._signal_profile.offset
        self._pin_step_data = np.full(sample_count, value)

    def _gen_linear_up(self, sample_count):
        '''สร้างสัญญาณไล่จาก min_amp → max_amp'''
        if sample_count <= 1:
            # สั้นเกินกว่าจะไล่ระดับได้ คืนค่าเดียว
            self._pin_step_data = np.array([self._signal_profile.min_amp])
        else:
            self._pin_step_data = np.linspace(self._signal_profile.min_amp, self._signal_profile.max_amp, sample_count)

    def _gen_linear_down(self, sample_count):
        '''สร้างสัญญาณไล่จาก max_amp → min_amp'''
        if sample_count <= 1:
            self._pin_step_data = np.array([self._signal_profile.max_amp])
        else:
            self._pin_step_data = np.linspace(self._signal_profile.max_amp, self._signal_profile.min_amp, sample_count)

    def _gen_digital_low(self, sample_count):
        '''สร้างสัญญาณ digital LOW (0V)'''
        self._pin_step_data = np.full(sample_count, self._signal_profile.min_amp)

    def _gen_digital_high(self, sample_count):
        '''สร้างสัญญาณ digital HIGH (amplitude V, default 3.3V)'''
        self._pin_step_data = np.full(sample_count, self._signal_profile.amplitude)

    def reset(self):
        self.signal_name = ""
        self._pin_step_data = np.array([])
        self.signal_profile.set_default()

    # def validate(self):
    #     if self.pin.pin_type != self.signal_profile.pin_type:
    #         raise ValueError("Pin Type and SignalProfile mismatch")
    #     self.signal_profile.validate()

    def clone(self):
        '''สร้าง copy ของ SignalProperties (copy profile + numpy array ด้วย)'''
        new_signal = SignalProperties(self._pin)
        new_signal.signal_name = self.signal_name
        new_signal._signal_profile = self._signal_profile.clone()
        new_signal._pin_step_data = self._pin_step_data.copy()
        return new_signal

    def __repr__(self):
        return (
            f"Signal Properties: Pin Name -> {self.pin.pin_name}\n"
            f"SignalType   -> {self.signal_profile}\n"
            f"Signal Name  -> {self.signal_name}\n"
            f"PIN enabled  -> {self.pin.enabled}\n"
        )


# ============================================================
# DataManager
# ============================================================
class DataManager:
    '''
    ที่เก็บ state ทั้งหมดของโปรแกรม (ชั้นข้อมูล)

        _pins    : dict[pin_name -> Pin]
        _steps   : list[StepBlock]
        _signals : dict[(pin_name, step_number) -> SignalProperties]  = ตาราง pin x step

    รวมถึง state ที่ GUI กำลังเลือกอยู่ (current_step, selected_pin)
    '''
    def __init__(self):
        # Data Stores
        self._pins    = {}       # dict[pin_name, Pin(pin_name)]
        self._steps   = []       # list[StepBlock]
        self._signals = {}       # dict[tuple[pin_name, step_index], SignalProperties]

        self._dt = 1 / 6400      # คาบเวลา sampling น้อยสุดที่บอร์ดทำได้ (วินาที)

        # GUI state
        self.current_step   = None  # int
        self.selected_pin   = None  # str

        self._init_software()

    def _init_software(self):
        # สร้าง state เริ่มต้นตอนเปิดโปรแกรม: 8 step + analog 4 ขา + digital _N/_P อย่างละ 11 ขา
        steps = 8
        pin_name = []
        analog_pin = 4
        digital_pin = 11  # _N, _P

        # add init steps
        for i in range(steps):
            self.add_step()

        # สร้างชื่อ Pin 
        for i in range(analog_pin):
            pin_name.append(f"AOUT_{i}")
        for i in range(digital_pin):
            pin_name.append(f"D_{i}_N")
        for i in range(digital_pin):
            pin_name.append(f"D_{i}_P")

        # add init pins
        for name in pin_name:
            self.add_pin(name)

    # ===================================
    # Read-only properties
    # ===================================
    @property
    def pins(self):
        return self._pins

    @property
    def steps(self):
        return self._steps

    @property
    def signals(self):
        return self._signals

    @property
    def dt(self):
        return self._dt

    # ==================================
    # Pin Methods
    # ==================================
    def add_pin(self, pin_name):
        # สร้าง Pin object
        if pin_name in self._pins:
            raise ValueError("Pin already exists")
        pin = Pin(pin_name)
        self._pins[pin_name] = pin
        # สร้าง Signal Propreties ให่ครบทุก step แล้วเชื่อม Signal Properties Object ทุก step เข้ากับ Pin Object
        for step in self._steps:
            key = (pin.pin_name, step.step_number)
            self._signals[key] = SignalProperties(pin)

    # def remove_pin(self, pin_name):
    #     if pin_name not in self._pins:
    #         raise KeyError(pin_name)

    #     # del Signal properties → steps
    #     for step in self._steps:
    #         key = (pin_name, step.step_number)
    #         del self._signals[key]

    #     # del Pin
    #     del self._pins[pin_name]

    def get_pin(self, pin_name):
        '''
        เอา Pin Object ตาม Parameter
        
        Pin_name : Pin name
        '''
        if pin_name not in self._pins:
            raise ValueError(f"{pin_name} is not pin data")
        return self._pins[pin_name]

    def set_pin_enabled(self, pin_name, enable):
        '''
        Set Enable ตาม Parameter
        
        Pin_name : Pin_name
        
        Enable : True/False
        '''
        pin = self.get_pin(pin_name)
        pin.enabled = enable

    # def enable_all(self):
    #     for pin in self._pins.values():
    #         pin.enable()

    # def disable_all(self):
    #     for pin in self._pins.values():
    #         pin.disable()

    def get_enabled_pins(self):
        '''
        เอา Pin object ทั้งหมดที่ Enable
        Output : List
        '''
        pins = []
        for pin in self._pins.values():
            if pin.enabled:
                pins.append(pin)
        return pins

    def get_pins_by_type(self, pin_type):
        '''
        เอา Pin Type ที่ตรงกับ Parameter
        Pin Type : Analog , Digital_N , Digital_P
        Output : List
        '''
        return [
            pin
            for pin in self._pins.values()
            if pin.pin_type == pin_type
        ]

    # =================================
    # Step Methods
    # =================================
    def add_step(self):
        # เพิ่ม Step object
        step = StepBlock(len(self._steps) + 1)
        self._steps.append(step)

        # Create Signal properties from _pins
        # for pin in self._pins.values():
        #     key = (pin.pin_name, step.step_number)
        #     self._signals[key] = SignalProperties(pin)  

        # def remove_step(self, step_no):  # แนะนำให้ลบ step สุดท้าย
        #     step = self.get_step(step_no)

        #     # del Signal in Step
        #     for pin in self._pins.values():
        #         del self._signals[(pin.pin_name, step_no)]

        #     # del Step
        #     self._steps.remove(step)

    def get_step(self, step_no):
        '''
        เอา Step ตาม Parameter
        step_no : int
        '''
        
        if not (1 <= step_no <= len(self._steps)):
            raise ValueError(f"Step out of range: 1 → {len(self._steps)}")
        # return Step Object ที่อยู่ใน DataManager 
        # ซึ่ง step_no ที่นำเข้ามาจะตรงกับ step_no - 1 ซึ่งเท่ากับ index ใน DataManager
        return self._steps[step_no - 1]

    def set_step_name(self, step_no, name):
        '''
        ใช้เซ็ต Step Name
        '''
        self.get_step(step_no).step_name = name

    def set_step_duration(self, step_no, duration):
        '''
        ใช้เซ็ต Step Duration
        '''
        self.get_step(step_no).duration = duration

    # def get_step_count(self):
    #     return len(self._steps)

    # =================================
    # Signal Properties Methods
    # =================================
    def get_signal_properties(self, pin_name, step_no):
        '''
        เอา Signal Properties ตาม Parameter
        Pin Name : str
        step No : int
        '''
        return self._signals[pin_name, step_no]

    def generate(self, pin_name, step_no):
        '''
        สั่งให้ Generate ค่าของ data ของแกน Y ใน Signal Propreties โดยใช้ Signal Profile , Step Duration , dt
        ซึ่ง Signal Propreties จะเป็นตัวของ Parameties :
        Pin name : str
        step no : int
        '''
        step = self.get_step(step_no)
        signal = self.get_signal_properties(pin_name, step_no)
        signal.gen_signal_data(step.duration, self._dt)

    def generate_all_for_step(self, step_no):
        '''อัปเดทค่าของสัญญาณตามแกน Y ของทุกขาที่ Enabld '''
        for pin in self.get_enabled_pins():
            self.generate(pin.pin_name, step_no)

    def get_pin_step_data(self, pin_name, step_no):
        '''
        เอา data ของแกน Y(numpy array) ของ Signal Propreties โดยใช้
        Parameter :
        Pin name : str
        Step no : int
        '''
        signal = self.get_signal_properties(pin_name, step_no)
        return signal.pin_step_data

    # =================================
    # Selection
    # =================================
    def set_current_step(self, step_no):
        '''
        set current step ตาม
        Parameter :
        Step no : int
        '''
        self.get_step(step_no)  # เช็คว่ามี step จริงไหม
        self.current_step = step_no

    def get_current_step(self):
        '''เอา current step ไปใช้ต่อ'''
        if self.current_step is None:
            raise ValueError("Current Step → None")
        return self.current_step

    def set_selected_pin(self, pin_name):
        '''
        set pin ที่เลือกตาม 
        Parameter :
        Pin name : str
        '''
        self.get_pin(pin_name)
        self.selected_pin = pin_name

    def get_selected_pin(self):
        '''เอา selected_pin ไปใช้ต่อ'''
        if self.selected_pin is None:
            raise ValueError("Selected Pin → None")
        return self.selected_pin
  

    # ==================================
    # Utility
    # ==================================
    def reset_all(self):
        ''' ล้างค่าทุกอย่างกลับเป็น default: Pin / step / Signal Propreties (แต่ไม่ลบตัว object ทิ้ง)'''
        # reset Pin Object
        for pin in self._pins.values():
            pin.reset()
        # reset Step Object
        for step in self._steps:
            step.reset()
        # reset Signal Propreties
        for signal in self._signals.values():
            signal.reset()

    def get_pin_data(self, pin_name):
        '''นำ data ของแกน Y ในทุก Step ของ Pin name มาต่อเรียงกันโดยจะคืนค่าเป็น numpy array'''
        
        # เอา Pin object มา
        pin = self.get_pin(pin_name)

        # เช็คว่า pin นั้น Enable = True ไหม
        if not pin.enabled:
            raise ValueError(f"{pin_name} is disabled")

        data = []
        # เอา data แต่ละ step มาต่อกันทุก step
        for step in self._steps:
            # ให้สร้าง data แกน Y ใหม่ก่อน
            self.generate(pin_name, step.step_number)

            step_data = self.get_pin_step_data(
                pin_name,
                step.step_number
            )
            # เพิ่ม numpy array ไปใน List
            if step_data is not None and step_data.size > 0:
                data.append(step_data)

        # ต่อ index ใน list เข้าด้วยกัน แล้วคืนค่าเป็น numpy array
        if data:
            return np.concatenate(data)

        return np.array([])

    def get_all_pin_data(self):
        '''
        เอา data ทุก Pin ที่ Enable แล้วคืนค่าเป็น dict
        ex {
                "AOUT_0": array([...]),
                "AOUT_1": array([...]),
                "DIO0_N": array([...]),
                ...
            }
        '''
        
        datas = {}
        for pin in self.get_enabled_pins():
            data = self.get_pin_data(pin.pin_name)
            datas[pin.pin_name] = data
            
        return datas
    def get_all_pin_data_for_send(self):
        '''
        รวมข้อมูลทุกขาที่ enable เป็น dict สำหรับส่งไปบอร์ด (จะถูกแปลงเป็น JSON)

        Returns:
        
            dict: {
                
                "dt": <float>,
                
                "sequence": [
                    {"pin": "AOUT_0", "data": [...]},   # analog แยกทีละขา
                    
                    {"pin": "GPIO_n", "data": [...]},   # digital กลุ่ม _N รวมเป็น bitmask
                    
                    {"pin": "GPIO_p", "data": [...]},   # digital กลุ่ม _P รวมเป็น bitmask
                ]
            }
            
        '''
        # เตรียม Format ตามที่ออกแบบไว้
        datas = {}
        datas["dt"] = self.dt
        datas["sequence"] = []

        # สร้าง ส่วนของ Analog pin
        for pin in self.get_pins_by_type(PinType.ANALOG):
            if pin.enabled:
                
                data = self.get_pin_data(pin.pin_name)
                
                if data is not None and data.size > 0:
                    datas["sequence"].append({
                        "pin": pin.pin_name,
                        "data": data.tolist()  #แปลงเป็น List
                        })
                
                
        # สร้างส่วนของ Digital pin
        # DIGITAL_N
        data_dn = self._merge_digital_group(PinType.DIGITAL_N)
        if data_dn:
            datas["sequence"].append({
                "pin": "GPIO_n", 
                "data": data_dn #คืนมาเป็น List แล้ว
            })
            
        # DIGITAL_P
        data_dp = self._merge_digital_group(PinType.DIGITAL_P)
        if data_dp:
            datas["sequence"].append({
                "pin": "GPIO_p", 
                "data": data_dp #คืนมาเป็น List แล้ว
            })
 
        return datas

    def _merge_digital_group(self, pin_type):
        '''
        รวมสัญญาณ digital เฉพาะกลุ่ม (N หรือ P) เป็นเลข bitmask ตัวเดียวต่อ 1 sample

        Returns:
            list | None: list ของเลข 11-bit, หรือ None ถ้าไม่มี pin ในกลุ่มนี้เปิดใช้เลย
        '''
        pin_data_list = []
        # เอา Pin object ที่มี Pintype ตรงกับ pin_type ที่ต้องการออกมา
        for pin in self.get_pins_by_type(pin_type):
            # เช็คว่า Pin enabled = True ไหม
            if not pin.enabled:
                continue
                
            raw_data = self.get_pin_data(pin.pin_name)
            
            
            signal_bits = (np.asarray(raw_data) > 0).astype(np.uint16)
            pin_data_list.append((pin.pin_index, signal_bits))

        if not pin_data_list:
            return None

        # ทุกขาที่ enabled มีความยาวข้อมูลเท่ากัน ใช้ตัวแรกเป็นตัวอ้างอิง
        total_samples = len(pin_data_list[0][1])
        merged = np.zeros(total_samples, dtype=np.uint16)

        # pack แต่ละขาเข้าบิตตาม pin_index -> ได้เลข 11-bit ตัวเดียวต่อ 1 sample
        for bit_index, bit_data in pin_data_list:
            merged |= bit_data << bit_index

        # list ของ data digital ที่ merge แล้ว
        return merged.tolist()

# ============================================================
# MainDialog (หน้าหลัก)
# ============================================================
class MainDialog(QDialog):
    '''
    หน้าต่างหลักของโปรแกรม

    - โหลด UI จาก WD_GUI.Ui_Dialog
    - ถือ DataManager 1 ตัวเป็นที่เก็บ state
    - ต่อ event ของปุ่ม/combobox เข้ากับเมธอด
    - มี QTimer เต้น ping เช็คการเชื่อมต่อบอร์ดทุก 1 วินาที
    '''

    def __init__(self):
        super().__init__()

        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

        # --- state เริ่มต้น ---
        # pending_signal: เก็บผลจาก popup ชั่วคราว
        self.pending_signal = None
        self.heart_beat_timer = QTimer(self)


        self.dm = DataManager()
        # set ค่าเริ่มต้นที่จะให้แสดงบน GUI
        self._init_start_gui()

        # เชื่อมต่อ object ไปยัง function
        self.ui.Step_no_comboBox.currentTextChanged.connect(self.on_step_changed)
        self.ui.Update_Step_Block_pushButton.clicked.connect(self.update_step_data)
        self.ui.Update_Signal_Properties_pushButton.clicked.connect(self.update_signal_properties)
        self.ui.Edit_Analog_signal_profile_pushButton.clicked.connect(self.open_edit_signal_profile)
        # self.ui.Edit_Digital_signal_profile_pushButton.clicked.connect(self.open_edit_signal_profile_digital)

        self.ui.reset_pushButton.clicked.connect(self.reset_all_data)
        self.ui.Combine_Signal_pushButton.clicked.connect(self.combine_signal)
        
        self.ui.run_pushButton.clicked.connect(self.run_button)
        self.ui.stop_pushButton.clicked.connect(self.stop_button)
        
        self.ui.connect_pushButton.clicked.connect(self.connect_button)
        self.ui.disconnect_pushButton.clicked.connect(self.disconnect_button)
        self.ui.poweroff_pushButton.clicked.connect(self.poweroff_button)
        
        # เพิ่ม signal profile บน GUI
        # self.ui.Analog_Signal_Profile_comboBox.addItem("Sine")
        # self.ui.Digital_Signal_Profile_comboBox.addItem("PWM")

        # สร้าง widget ต่อขา (checkbox / ปุ่ม / กราฟ) ตามรายชื่อขาใน DataManager
        self._init_checkboxes()
        self._init_pin_button()
        self._init_plot()


        # เชื่อม function ที่จะทำงานเมื่อเกิด time_out ของ QTimer
        self.heart_beat_timer.timeout.connect(self.check_connecttion_stetus)

    # ================================
    #   INIT GUI
    # ================================
    def _init_start_gui(self):
        # ตั้งค่าหน้าจอเริ่มต้น: step 1, เลือกขาแรกใน dict, สถานะ disconnected, โหลดข้อมูล step 1
        self.dm.set_current_step(1)
        self.ui.Step_no_comboBox.setCurrentIndex(0)
        first_pin = list(self.dm.signals.keys())[0][0]  # pin name ตัวแรกใน dict
        self.dm.set_selected_pin(first_pin)
        self.ui.Show_Pin_label.setText(first_pin)
        self.ui.status_board_label.setText("status : disconnected")
        self.load_step_data(self.dm.current_step)
    
        # ตั้งค่า ขนาด Font ของ Log ทั้งสองช่อง
        self.ui.log_data_textBrowser.setStyleSheet("""font-size: 10px;""")
        self.ui.log_reply_textBrowser.setStyleSheet("""font-size: 10px;""")

    def _init_checkboxes(self):
        # หา checkbox ของแต่ละขาจาก self.ui ตามชื่อ (เช่น "AOUT_0_checkBox") แล้วเก็บใส่ dict
        self.pin_checkboxes = {}
        for pin_name in self.dm.pins:
            checkbox = getattr(self.ui, f"{pin_name}_checkBox")
            self.pin_checkboxes[pin_name] = checkbox

            checkbox.toggled.connect(
                lambda checked, name=pin_name: self.on_pin_checked(checked, name)
            )

    def _init_pin_button(self):
        # หา pushButton ที่ใช้ในการตั้งค่า Signal profile ของแต่ละขาจาก self.ui ตามชื่อ (เช่น "AOUT_0_pushButton") แล้วเก็บใส่ dict
        self.pin_button = {}
        for pin_name in self.dm.pins:
            button = getattr(self.ui, f"{pin_name}_pushButton")
            self.pin_button[pin_name] = button

            button.clicked.connect(
                lambda checked=False, name=pin_name: self.on_pin_button_clicked(name)
            )

    def _init_plot(self):
        # หา widget ที่ใช้ในการ show กราฟ ของแต่ละขาจาก self.ui ตามชื่อ (เช่น "AOUT_0_show_widget") แล้วเก็บใส่ dict
        self.plot_widgets = {}
        for pin_name in self.dm.pins:
            widget = getattr(self.ui, f"{pin_name}_show_widget")
            self.plot_widgets[pin_name] = widget

            # setting widget init
            self._setup_plot_widget(pin_name, widget)

    def _setup_plot_widget(self, pin_name, widget):
        # ตั้งค่าเริ่มต้นของ Widget ที่ใช้ในการ plot กราฟ
        widget.clear()
        widget.showGrid(x=True, y=True)
        widget.getPlotItem().hideButtons()
        widget.setMenuEnabled(False)
        widget.setMouseEnabled(x=False, y=False)

        pin = self.dm.get_pin(pin_name)

        if pin.is_analog():
            widget.setYRange(0, 2.5, padding=0)
        else:
            widget.setYRange(0, 4, padding=0)


        widget.setXRange(0, 1, padding=0)
        widget.enableAutoRange(axis="x")
        widget.enableAutoRange(axis="y")

    # =================================
    # STEP BLOCK
    # =================================
    def on_step_changed(self, step_no):
        '''
        ทำงานเมื่อผู้ใช้เปลี่ยน step จาก comboBox
        '''
        self.pending_signal = None
        step_no = int(step_no)
        self.dm.set_current_step(step_no)
        self.load_step_data(step_no)
        self.load_signal_properties()
        self.update_plot()

    def load_step_data(self, step_no):
        '''
        โหลดข้อมูลจาก DataManager -> ช่องกรอก Step name /Step Duration
        '''
        data_step = self.dm.get_step(step_no)
        self.ui.Block_Name_lineEdit.setText(data_step.step_name)
        self.ui.Duration_Time_lineEdit.setText(str(data_step.duration))

    def update_step_data(self):
        '''จะทำเมื่อกดปุ่ม Update Step Block'''
        # หา current step และ selected pin เพื่อ Load ข้อมูลแสดงบน GUI 
        step_update = self.dm.get_current_step()
        update_data_step = self.dm.get_step(step_update)

        # โหลดค่าจาก DtaManager -> GUI
        update_data_step.step_name = self.ui.Block_Name_lineEdit.text()
        duration_update = float(self.ui.Duration_Time_lineEdit.text())
        # เช็คว่า duration >= 0 
        if duration_update >= 0:
            update_data_step.duration = duration_update
        else:
            self.ui.log_data_textBrowser.append("Duration must be >= 0")

        # เขียน log Display ลง textBrowser ว่ามีการแก้ไข step ไหน ชื่ออะไร และ duration เท่าไหร่
        self.ui.log_data_textBrowser.append(
            f"Updated step  {update_data_step.step_number} : step name  ->  {update_data_step.step_name}  ,  step duration ->  {update_data_step.duration} s"
        )
        # พล็อตกราฟใหม่เนื่องจากแก้ไข duration time
        self.update_plot()

    # =================================
    # CHECKBOX
    # =================================
    def on_pin_checked(self, checked, pin_name):
        '''
        ติ๊ก/เอาติ๊กออก checkbox ของขา -> enable/disable ขานั้นแล้ววาดกราฟใหม่
        '''
        pin = self.dm.get_pin(pin_name)
        if checked:
            pin.enable()
        else:
            pin.disable()

        self.update_plot()

    # ==================================
    # SIGNAL PROPERTIES
    # ==================================
    def on_pin_button_clicked(self, pin_name):
        '''
        กดปุ่มชื่อขา -> ตั้งเป็นขาที่กำลังแก้ แล้วโหลด signal ของขานั้นขึ้น GUI
        '''
        self.dm.set_selected_pin(pin_name)
        self.load_signal_properties()
        
        # เคลียร์ pending_signal เพราะผู้ใช้เปลี่ยนขาแล้ว
        self.pending_signal = None

    def update_signal_properties(self):
        '''จะทำเมื่อกดปุ่ม Update Signal Properties'''
        # หา current step และ selected pin เพื่อ update ข้อมูลใน DataManager จาก GUI
        step_no = self.dm.get_current_step()
        selected_pin = self.dm.get_selected_pin()
        # เอา Signal Properties ของขาที่เลือก + step ปัจจุบัน
        signal = self.dm.get_signal_properties(selected_pin, step_no)

        # อัปเดตชื่อ signal name ลง DataManager
        signal.signal_name = self.ui.Signal_Name_lineEdit.text()
        
        # ถ้ามี pending_signal (มาจาก popup) ให้เอา signal profile ของ pending_signal มาอัปเดตลง DataManager
        if self.pending_signal is not None:
            # Update from Popup
            signal.signal_profile = self.pending_signal.signal_profile
            
            if signal.signal_profile.signal_type == SignalTypeAnalog.CONSTANT:
                self.ui.log_data_textBrowser.append(
                        f"Updated : {signal.pin.pin_name}    "
                        f"Step : {step_no} \n"
                        f"Signal Name : {signal.signal_name}   "
                        f"Signal Profile -> {signal.signal_profile.signal_type.value} \n"
                        f"Parameter -> Amp : {signal.signal_profile.amplitude} V    offset : {signal.signal_profile.offset} V \n"
                    )
                
            if signal.signal_profile.signal_type in (SignalTypeAnalog.LINEAR_DOWN , SignalTypeAnalog.LINEAR_UP):
                self.ui.log_data_textBrowser.append(
                        f"Updated : {signal.pin.pin_name}    "
                        f"Step : {step_no} \n"
                        f"Signal Name : {signal.signal_name}   "
                        f"Signal Profile -> {signal.signal_profile.signal_type.value} \n"
                        f"Parameter ->  Max_Amp : {signal.signal_profile.max_amp} V  Min_Amp : {signal.signal_profile.min_amp} \n"
                    )
        # ถ้าไม่มี pending_signal ให้เอาค่าจาก comboBox ของ GUI มาอัปเดตลง DataManager
        else:
            if signal.pin.is_analog():
                signal.signal_profile.set_signal_type(
                    SignalTypeAnalog(
                        self.ui.Analog_Signal_Profile_comboBox.currentText()
                    )
                )
                
                if signal.signal_profile.signal_type == SignalTypeAnalog.CONSTANT:
                    self.ui.log_data_textBrowser.append(
                            f"Updated : {signal.pin.pin_name}    "
                            f"Step : {step_no} \n"
                            f"Signal Name : {signal.signal_name}   "
                            f"Signal Profile -> {signal.signal_profile.signal_type.value} \n"
                            f"Parameter -> Amp : {signal.signal_profile.amplitude} V    offset : {signal.signal_profile.offset} V \n"
                        )
                
                if signal.signal_profile.signal_type in (SignalTypeAnalog.LINEAR_DOWN , SignalTypeAnalog.LINEAR_UP):
                    self.ui.log_data_textBrowser.append(
                            f"Updated : {signal.pin.pin_name}    "
                            f"Step : {step_no} \n"
                            f"Signal Name : {signal.signal_name}   "
                            f"Signal Profile -> {signal.signal_profile.signal_type.value} \n"
                            f"Parameter ->  Max_Amp : {signal.signal_profile.max_amp} V  Min_Amp : {signal.signal_profile.min_amp} \n"
                        )
                                
            elif signal.pin.is_digital():
                signal.signal_profile.set_signal_type(
                    SignalTypeDigital(
                        self.ui.Digital_Signal_Profile_comboBox.currentText()
                    )
                )
                
                self.ui.log_data_textBrowser.append(  
                        f"Updated : {signal.pin.pin_name}    "
                        f"Step : {step_no} \n"
                        f"Signal Name : {signal.signal_name}   "
                        f"Signal Profile -> {signal.signal_profile.signal_type.value} \n"
                    )
        # เคลียร์ pending_signal เพราะอัปเดตเสร็จแล้ว
        self.pending_signal = None

        # update plot ใหม่เพราะ signal profile อาจเปลี่ยนไปแล้ว
        self.update_plot()

    def load_signal_properties(self):
        '''โหลดข้อมูลจาก DataManager (Signal Properties) มาแสดงบน GUI'''
        # หา current step และ selected pin เพื่อ Load ข้อมูลแสดงบน GUI
        step_no = self.dm.get_current_step()
        selected_pin = self.dm.get_selected_pin()
        # เอา Signal Properties ของขาที่เลือก + step ปัจจุบัน
        signal = self.dm.get_signal_properties(selected_pin, step_no)

        # โหลดข้อมูลจาก DataManager มาแสดงบน GUI (Pin name / Signal name / Signal profile)
        self.ui.Show_Pin_label.setText(signal.pin.pin_name)
        self.ui.Signal_Name_lineEdit.setText(signal.signal_name)

        # โหลด signal profile ของขาที่เลือก
        # ถ้าเป็น analog ให้แสดงหน้าจอ Analog และเลือก signal profile ตาม AnalogSignalProfile
        if signal.pin.is_analog():
            # แสดง ComboBox Analog
            self.ui.Signal_Profile_stackedWidget.setCurrentWidget(
                self.ui.Analog_pin_type_page
            )
            # แสดง signal profile จาก DataManager ใน ComboBox ของ GUI
            self.ui.Analog_Signal_Profile_comboBox.setCurrentText(signal.signal_profile.signal_type.value)
        # ถ้าเป็น digital ให้แสดงหน้าจอ Digital และเลือก signal profile ตาม DigitalSignalProfile
        elif signal.pin.is_digital():
            # แสดง ComboBox Digital
            self.ui.Signal_Profile_stackedWidget.setCurrentWidget(
                self.ui.Digital_pin_type_page
            )
            
            # แสดง signal profile จาก DataManager ใน ComboBox ของ GUI
            self.ui.Digital_Signal_Profile_comboBox.setCurrentText(signal.signal_profile.signal_type.value)

        # else:
        #     raise TypeError(f"Invalid Pin Type: {signal.pin.pin_type}")

    # ====================================
    # POPUP
    # ====================================
    def open_edit_signal_profile(self):
        '''เปิด popup เพื่อแก้ไข signal profile ของขาที่เลือก'''
        # หา current step และ selected pin
        step_no = self.dm.get_current_step()
        selected_pin = self.dm.get_selected_pin()
        # เอา Signal Properties ของขาที่เลือก + step ปัจจุบัน
        signal = self.dm.get_signal_properties(selected_pin, step_no)
        
        # Copy Signal Properties ของขาที่เลือก + step ปัจจุบัน เพื่อส่งไปยัง popup (ไม่แก้ไข DataManager โดยตรง)
        templ_signal = signal.clone()

        # เลือก signal profile ของ popup ตามประเภทของขา (analog / digital) ตาม DataManager แต่ของ digital ยังไม่มีความจำเป็นต้องเปิด
        if signal.pin.is_analog():
            # เลือก signal profile ของ popup ตามประเภทของขา (analog) ตาม ComboBox ของ GUI
            profile_text = self.ui.Analog_Signal_Profile_comboBox.currentText()
            templ_signal.signal_profile.set_signal_type(
                SignalTypeAnalog(profile_text)
            )
            # เปิด popup ของ Analog
        popup = SetupPopup(templ_signal, self)

        # ถ้า popup ถูกกด OK ให้เอา signal profile ของ popup มาอัปเดตลง self.pending_signal เพื่อให้ update_signal_properties() เอาไปอัปเดตลง DataManager
        if popup.exec():
            self.pending_signal = popup.signal
            print("OK")
        # ถ้า popup ถูกกด Cancel ให้ไม่ทำอะไร
        else:
            print("Popup Cancel")

    # ====================================
    # Plot
    # ====================================
    def update_plot(self):
        '''อัปเดตกราฟของทุกขาที่ Enable'''
        # หา current step เพื่อ Generate data ของทุกขาที่ Enable
        step_no = self.dm.get_current_step()
        # อัปเดทค่าของ data ของแกน Y ใน Signal Propreties ของทุกขาที่ Enable
        self.dm.generate_all_for_step(step_no)

        # อัปเดตกราฟของทุกขาที่ Enable
        for pin_name, widget in self.plot_widgets.items():
            widget.clear()
            pin = self.dm.get_pin(pin_name)
            if pin.enabled:
                data = self.dm.get_pin_step_data(pin_name, step_no)
                if len(data) > 0:
                    x = np.arange(len(data)) * self.dm.dt
                    y = np.array(data)
                        
                    widget.plot(x, y, pen=pg.mkColor("y"))
                    if pin.is_analog():
                        widget.setYRange(0, max(y) + 0.5, padding=0)
                    else:
                        widget.setYRange(0, 3.5, padding=0)
                        
                    widget.setXRange(0, float(x[-1]), padding=0)

    # ===================================
    # BOARD BUTTON
    # ====================================
    # กด connect
    def connect_button(self):
        '''ทำงานเมื่อกดปุ่ม Connect'''
        # เอา IP address จาก comboBox ของ GUI
        host_name_ip = self.ui.host_name_comboBox.currentText()
        
        # เช็คว่า IP address ไม่ว่างเปล่า
        if not host_name_ip:
            self.ui.log_data_textBrowser.append("The IP should not be empty")
            return
        else:
            # เรียก connect_board() จาก WD_GUI_communication.py เพื่อเชื่อมต่อบอร์ด
            ret, reply_gui = connect_board(host_name_ip)
            self.ui.log_reply_textBrowser.append(reply_gui)
            # ถ้าเชื่อมต่อสำเร็จ ให้เริ่ม QTimer เพื่อเช็คการเชื่อมต่อทุก 1 วินาที
            if ret:
                self.heart_beat_timer.start(1000)
            
    def check_connecttion_stetus(self):
        '''เช็คการเชื่อมต่อบอร์ด'''
        # โดยจะทำงานทุกครั้งที่เกิด time_out ของ QTimer (ปัจุบัน ทุก 1 วินาที)
        connection_status , signal_state = check_connection_status()
        print(connection_status, "  " , signal_state)
        # อัปเดตสถานะการเชื่อมต่อบน GUI และ log ข้อความถ้าเกิดการตัดการเชื่อมต่อ
        if connection_status:
            self.ui.status_board_label.setText("status : connected")
        else:
            self.ui.status_board_label.setText("status : disconnected")
            self.ui.log_reply_textBrowser.append("[ERROR] Connection Loss")
            self.heart_beat_timer.stop()
        
        # แสดงข้อความสถานะของการสร้างสัญญาณจากบอร์ดโดยจะมาเมื่อการสร้างสัญญาณเสร็จสิ้น ลงใน log_reply_textBrowser
        if signal_state is not None:
            self.ui.log_reply_textBrowser.append(signal_state)   
        
    
        
        # กด disconnect
    def disconnect_button(self):
        '''ทำงานเมื่อกดปุ่ม Disconnect'''
        # เรียก disconnect_board() จาก WD_GUI_communication.py เพื่อยกเลิกการเชื่อมต่อบอร์ด
        ret, reply_gui = disconnect_board()
        self.ui.log_reply_textBrowser.append(reply_gui)
        # ถ้ายกเลิกการเชื่อมต่อสำเร็จ ให้หยุด QTimer และอัปเดตสถานะการเชื่อมต่อบน GUI
        if ret:
            self.heart_beat_timer.stop()
            self.ui.status_board_label.setText("status : disconnected")
            
        
        #  poweroff
    def poweroff_button(self):
        '''ทำงานเมื่อกดปุ่ม Power Off'''
        # เรียก poweroff_board() จาก WD_GUI_communication.py เพื่อสั่งปิดบอร์ด
        ret, reply_gui = poweroff_board()
        self.ui.log_reply_textBrowser.append(reply_gui)
        # ถ้าปิดบอร์ดสำเร็จ ให้หยุด QTimer และอัปเดตสถานะการเชื่อมต่อบน GUI
        if ret:
            self.heart_beat_timer.stop()
            self.ui.status_board_label.setText("status : disconnected")
        
        #  Run
    def run_button(self):
        # เอา data ของทุกขาที่ Enable แล้วรวมเป็น dict สำหรับส่งไปบอร์ด
        input_parameter_signal = self.dm.get_all_pin_data_for_send()
        # เรียก run_signal_gen_wd() จาก WD_GUI_communication.py เพื่อสั่งให้บอร์ดสร้างสัญญาณตามข้อมูลที่ส่งไป
        ret, reply_gui = run_signal_gen_wd(input_parameter_signal)
        self.ui.log_reply_textBrowser.append(reply_gui)
        
        # Stop
    def stop_button(self):
        # เรียก stop_signal_gen_wd() จาก WD_GUI_communication.py เพื่อสั่งให้บอร์ดหยุดสร้างสัญญาณ
        ret, reply_gui = stop_signal_gen_wd()
        self.ui.log_reply_textBrowser.append(reply_gui)
    
    def save_log_file(self):
        '''
        เซฟ log ทั้ง 2 ช่อง (display + communication) ลงไฟล์ Output/Log_file_<timestamp>.txt
        เขียนไฟล์เฉพาะเมื่อมี log อย่างน้อย 1 ช่อง
        '''
        # สร้าง timestamp สำหรับชื่อไฟล์
        current_datetime = datetime.now()
        datetime_string = current_datetime.strftime("%Y%m%d_%H%M%S")
        
        # เอา log ทั้ง 2 ช่องมาเก็บในตัวแปร
        log_display = self.ui.log_data_textBrowser.toPlainText()
        log_communucation = self.ui.log_reply_textBrowser.toPlainText()
        # เขียน log ลงไฟล์เฉพาะเมื่อมี log อย่างน้อย 1 ช่อง
        if log_display or log_communucation:
            with open(f"Output/Log_file_{datetime_string}.txt", "w") as f:
                f.write("Log Display\n")
                f.write(log_display)
                f.write("\n\n")
                f.write("Log Communication\n")
                f.write(log_communucation)
    
    def reset_all_data(self):
        '''reset ข้อมูลทั้งหมดใน DataManager และ refresh GUI ให้กลับไปเป็นค่าเริ่มต้น'''
        # save log file ก่อนเคลียร์ข้อมูลทั้งหมด
        self.save_log_file()
        # เคลียร์ DataManager
        self.dm.reset_all()

        # เคลียร์ state
        self.pending_signal = None
        
        # เคลียร์ GUI
        self.dm.set_current_step(1)
        first_pin = list(self.dm.signals.keys())[0][0]
        self.dm.set_selected_pin(first_pin)

        # เคลียร์ทุก plot
        for pin_name, widget in self.plot_widgets.items():
            self._setup_plot_widget(pin_name, widget)
    

        # เคลียร์ทุก checkbox
        for checkbox in self.pin_checkboxes.values():
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)

        # เคลียร์ Step_no_comboBox ให้กลับไปเป็น step 1
        self.ui.Step_no_comboBox.blockSignals(True)
        self.ui.Step_no_comboBox.setCurrentIndex(0)
        self.ui.Step_no_comboBox.blockSignals(False)

        # โหลด UI จาก step 1 
        self.load_step_data(1)
        self.load_signal_properties()

        # เคลียร์ log ทั้ง 2 ช่อง
        self.ui.log_data_textBrowser.clear()
        self.ui.log_reply_textBrowser.clear()

    def combine_signal(self):
        '''
        gen ทุกขาทุก step -> รวมข้อมูล -> เปิด CombinePlotDialog แสดงกราฟรวมสัญญาณของทุกขา(ที่ Enable)
        '''
        # update data ของทุกขาที่ Enable ในทุก step
        for step in self.dm.steps:
            self.dm.generate_all_for_step(step.step_number)

        # เอา data ของทุกขาที่ Enable ในทุก step มารวมเป็น dict
        all_data = self.dm.get_all_pin_data()
        
        # นับจำนวน sample ทั้งหมดของทุกขาที่ Enable ในทุก step
        total_combined_samples  = 0
        for v in all_data.values():
            total_combined_samples += len(v)
        
        # คำนวณ total_duration ของทุก step
        total_duration = 0
        for d in self.dm.steps:
            total_duration += d.duration
        
        # เปิด CombinePlotDialog แสดงกราฟรวมสัญญาณของทุกขา(ที่ Enable) โดยส่ง all_data, dt, total_duration ไปให้
        dialog = CombinePlotDialog(all_data, self.dm.dt, total_duration, self)
        dialog.exec()
        
    def on_quit(self):
        '''ทำงานเมื่อปิดโปรแกรม -> save log file ก่อนปิด'''
        self.save_log_file()

        
# ============================================================
# CombinePlotDialog (หน้าต่าง plot รวมทุก pin ทุก step)
# ============================================================
class CombinePlotDialog(QDialog):
    '''
    หน้าต่าง plot รวม แสดงสัญญาณของทุกขา (ต่อจากทุก step) แยกกราฟละ 1 ขา
    ใน scroll area พร้อม info bar สรุป duration / dt / จำนวนขา
    '''

    def __init__(self, all_data, dt, total_duration, parent=None):
        super().__init__(parent)
        # หาจำนวนขาที่จะแสดง เพื่อไปกำหนดความสูงของหน้าต่าง และ จำนวนกราฟที่จะสร้าง
        pin_count = len(all_data)
        # ตั้งชื่อหน้าต่าง และขนาดหน้าต่าง
        self.setWindowTitle("Combined Signal")
        self.resize(1000, min(200 * pin_count + 50, 800))

        # ---สร้าง Scroll area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        # เก็บ layout ของกราฟทั้งหมดใน QWidget แล้วใส่ลงใน scroll area
        container = QWidget()
        self._pin_layout = QVBoxLayout(container)
        self._pin_layout.setSpacing(10)
        self._pin_layout.setContentsMargins(5, 1, 5, 1)

        scroll.setWidget(container)

        # --สร้าง layout หลักของ CombinePlotDialog ---
        layout = QVBoxLayout(self)
        layout.addWidget(scroll)

        # ---สร้าง Info bar ---
        info_text = (
            f"Total duration: {total_duration:.2f}s    |    "
            f"dt: {dt * 1000} ms   |    "
            f"Pins: {pin_count}"
        )
        # สร้าง label สำหรับ info bar
        info_label = QLabel(info_text)
        info_label.setStyleSheet("padding: 4px; font-size: 13px;")
        layout.addWidget(info_label)

        # --- สร้างกราฟแยกต่อ pin ---
        for pin_name, data in all_data.items():
            self._add_pin_plot(pin_name, data, dt)

    def _add_pin_plot(self, pin_name, data, dt):
        '''สร้าง PlotWidget 1 อันสำหรับ 1 pin แล้วเพิ่มลง layout'''
        pw = pg.PlotWidget()
        pw.setLabel("left", "V")
        pw.setLabel("bottom", "Time", units="s")
        pw.showGrid(x=True, y=True)
        pw.setMenuEnabled(False)
        pw.setMouseEnabled(x=False, y=False)

        # Title เป็นชื่อ pin (ซ้ายบนของกราฟ)
        pw.setTitle(f"{pin_name}", color=(255, 255, 255), size="12pt")

        #  plot data
        if len(data) > 0:
            x = np.arange(len(data)) * dt
            y = np.array(data)
            pw.plot(x, y, pen=pg.mkPen(color='y'))
            
            if pin_name.startswith("AOUT"):
                pw.setYRange(0, max(y) + 0.5, padding=0)
            else:
                pw.setYRange(0, 3.5, padding=0)
                        
            pw.setXRange(0, float(x[-1])+0.5, padding=0)


        # ตั้งความสูงขั้นต่ำให้ดูง่าย
        pw.setMinimumHeight(180)

        self._pin_layout.addWidget(pw)


# ============================================================
# SetupPopup (Dialog ตั้งค่า Signal Profile)
# ============================================================
class SetupPopup(QDialog):
    '''
    Dialog ตั้งค่าพารามิเตอร์ของ Signal Profile
    '''

    def __init__(self, signal_properties, parent=None):
        super().__init__(parent)
        self.signal = signal_properties

        self.ui = SetupSignal()
        self.ui.setupUi(self)

        self._load_signal()
        self._update_page()

    def _load_signal(self):
        '''เอาค่าจาก SignalProfile ปัจจุบันมาใส่ช่องกรอกใน dialog'''
        # โหลดค่าจาก SignalProfile ปัจจุบันมาใส่ช่องกรอกใน dialog
        # Pin name
        self.ui.Pin_name_setup_label.setText(self.signal.pin.pin_name)
        # Signal profile
        self.ui.Signal_Profile_setup_label.setText(
            self.signal.signal_profile.signal_type.value
        )
        # Min Amplitude
        self.ui.Min_Amplitude_lineEdit.setText(
            str(self.signal.signal_profile.min_amp)
        )
        # Max Amplitude
        self.ui.Max_Amplitude_lineEdit.setText(
            str(self.signal.signal_profile.max_amp)
        )
        # Amplitude
        self.ui.Amplitude_lineEdit.setText(
            str(self.signal.signal_profile.amplitude)
        )
        # Offset
        self.ui.Offset_lineEdit.setText(
            str(self.signal.signal_profile.offset)
        )

    def _update_page(self):
        '''สลับหน้า stackedWidget ให้ตรงกับ signal_type'''
        signal_type = self.signal.signal_profile.signal_type

        if signal_type == SignalTypeAnalog.CONSTANT:
            self.ui.stackedWidget.setCurrentIndex(0)

        elif signal_type in (SignalTypeAnalog.LINEAR_UP, SignalTypeAnalog.LINEAR_DOWN):
            self.ui.stackedWidget.setCurrentIndex(1)
            
        # add edit signal profile ใหม่

    def accept(self):
        '''กด OK -> เซฟค่าตามชนิดสัญญาณ (dispatch ไป _save_constant / _save_linear) แล้วปิด dialog'''
        signal_type = self.signal.signal_profile.signal_type

        if signal_type == SignalTypeAnalog.CONSTANT:
            self._save_constant()
        elif signal_type in (SignalTypeAnalog.LINEAR_UP, SignalTypeAnalog.LINEAR_DOWN):
            self._save_linear()
        elif signal_type in (SignalTypeDigital.LOW, SignalTypeDigital.HIGH):
            self._save_constant()

        super().accept()

    def _save_constant(self):
        '''อ่าน Amplitude / Offset จากช่องกรอก เขียนกลับลง profile'''
        profile = self.signal.signal_profile
        profile.amplitude = float(self.ui.Amplitude_lineEdit.text())
        profile.offset = float(self.ui.Offset_lineEdit.text())

    def _save_linear(self):
        '''อ่าน Min / Max Amplitude จากช่องกรอก เขียนกลับลง profile'''
        profile = self.signal.signal_profile
        profile.min_amp = float(self.ui.Min_Amplitude_lineEdit.text())
        profile.max_amp = float(self.ui.Max_Amplitude_lineEdit.text())
        


# ========================
# Main
# ========================
if __name__ == "__main__":
    import sys
    # ตั้งค่า QApplication และเปิดหน้าต่างหลัก MainDialog
    app = QApplication(sys.argv)

    window = MainDialog()
    window.show()
    # เมื่อปิดโปรแกรม ให้เรียก on_quit() เพื่อ save log file ก่อนปิด
    app.aboutToQuit.connect(window.on_quit)

    sys.exit(app.exec())

