#   RP_Create_signal.py
#   ชั้นที่คุยกับฮาร์ดแวร์ Red Pitaya โดยตรง
#
#   งานหลัก 2 อย่าง:
#       calculate_signal_setting() - แปลง sequence (pin + ข้อมูล) จาก client
#                                    เป็นรายการฟังก์ชันพร้อมอาร์กิวเมนต์
#       send_signal_to_pinout()    - วนส่งข้อมูลออกขาจริงทีละ sample ตามจังหวะ dt
#
#   ประเภทขา:
#       analog  (AOUT_0..AOUT_3)  -> rp.rp_ApinSetValue(channel, value)
#       digital (GPIO_n / GPIO_p) -> rp.rp_GPIOnSetState / rp.rp_GPIOpSetState(bitmask)

import rp
import time

rp.rp_Init()                             # ฟังก์ชันที่ใช้ เปิดการเชื่อมต่อกับฮาร์ดแวร์ Red Pitaya
rp.rp_ApinReset()                        # reset ขา slow analog 0-3 ให้ volt = 0
rp.rp_DpinReset()                        # reset ขา GPIO 22 pin (GPIOn, GPIOp) ให้ volt = 0
rp.rp_GPIOnSetDirection(0b11111111111)   # ตั้งขา GPIO_n ทั้งหมดเป็น output
rp.rp_GPIOpSetDirection(0b11111111111)   # ตั้งขา GPIO_p ทั้งหมดเป็น output
rp.rp_GPIOnSetState(0b00000000000)
rp.rp_GPIOpSetState(0b00000000000)

# =================================
# Calculate
# =================================

def calculate_signal_setting(input_parameter_signal):
    '''
    
    แปลง sequence จาก client เป็นรายการฟังก์ชันที่เรียกใช้ได้
    (map ชื่อ pin -> ฟังก์ชันของไลบรารี rp พร้อมเก็บ channel/ข้อมูลเป็น tuple)

    Parameters:
        input_parameter_signal (dict): {
            "dt": <วินาที/sample>,
            "sequence": [{"pin": <str>, "data": [<ค่าแต่ละ sample>]}, ...]
        }

    Returns:
        (status, dt, functions_analog, functions_digital)
            status (bool)               : True ถ้าทุก pin รู้จัก, False ถ้าเจอ pin แปลก
            functions_analog (list) : [(rp.rp_ApinSetValue, channel, data), ...]
            functions_digital (list): [(rp.rp_GPIOnSetState/rp_GPIOpSetState, data), ...]
        เมื่อ status เป็น False ค่าที่เหลือทั้งหมดเป็น None
        
    '''
    dt = input_parameter_signal["dt"]

    functions_analog = []
    functions_digital = []

    group_data = input_parameter_signal["sequence"]
    for index in group_data:
        pin = index["pin"]
        data = index["data"]
        if pin == "AOUT_0":
            functions_analog.append((rp.rp_ApinSetValue, 0, data))
        elif pin == "AOUT_1":
            functions_analog.append((rp.rp_ApinSetValue, 1, data))
        elif pin == "AOUT_2":
            functions_analog.append((rp.rp_ApinSetValue, 2, data))
        elif pin == "AOUT_3":
            functions_analog.append((rp.rp_ApinSetValue, 3, data))
        elif pin == "GPIO_n":
            functions_digital.append((rp.rp_GPIOnSetState, data))
        elif pin == "GPIO_p":
            functions_digital.append((rp.rp_GPIOpSetState, data))
        else:
            return False, None, None, None

    return True, dt, functions_analog, functions_digital


# =================================
# Send to pinout
# =================================

def send_signal_to_pinout(stop_event, dt, functions_analog, functions_digital):
    '''
    
    เตรียมฮาร์ดแวร์ (init + reset + ตั้ง GPIO เป็น output) แล้วเลือกโหมดส่งตามชนิดข้อมูล
    บล็อก finally: reset ขาทั้งหมดเมื่อจบไม่ว่ากรณีใด

    Parameters:
        stop_event (threading.Event): flag สำหรับสั่งหยุดกลางคัน
        dt (float): ระยะเวลาต่อ 1 sample (วินาที)
        functions_analog (list): จาก calculate_signal_setting()
        functions_digital (list): จาก calculate_signal_setting()
        
    '''
    try:
        # rp.rp_Init()                             # ฟังก์ชันที่ใช้ เปิดการเชื่อมต่อกับฮาร์ดแวร์ Red Pitaya
        # rp.rp_ApinReset()                        # reset ขา slow analog 0-3 ให้ volt = 0
        # rp.rp_DpinReset()                        # reset ขา GPIO 22 pin (GPIOn, GPIOp) ให้ volt = 0
        # rp.rp_GPIOnSetDirection(0b11111111111)   # ตั้งขา GPIO_n ทั้งหมดเป็น output
        # rp.rp_GPIOpSetDirection(0b11111111111)   # ตั้งขา GPIO_p ทั้งหมดเป็น output

        # เลือกว่าจะสร้างสัญญาณแบบไหน
        if functions_analog:
            if functions_digital:
                # สร้างสัญญาณ Analog , Digital
                analog_digital(stop_event, dt, functions_analog, functions_digital)
            else:
                # สร้างสัญญาณ Analog อย่างเดียว
                analog_only(stop_event, dt, functions_analog)
        elif functions_digital:
            # สร้างสัญญาณ Digital อย่างเดียว
            digital_only(stop_event, dt, functions_digital)
    finally:
        # reset ขา Slow Analog , GPIO ให้ Volt เป็น 0 หลังการสร้างสัญญาณเสร็จ
        rp.rp_ApinReset()
        # rp.rp_DpinReset()
        rp.rp_GPIOnSetState(0b00000000000)
        rp.rp_GPIOpSetState(0b00000000000)


# 3 โหมดข้างล่างวน sample เดียวกัน ต่างกันแค่ชนิดข้อมูลที่ส่ง
# จับจังหวะเวลาโดยใช้ Busy wait
# และเช็ค stop_event ระหว่างรอ เพื่อออกจากลูปได้ทันทีเมื่อถูกสั่งหยุด

def analog_digital(stop_event, dt, functions_analog, functions_digital):
    '''
    
    ส่งข้อมูลทั้ง analog และ digital พร้อมกันทีละ sample
    (จำนวน sample อ้างอิงจากชุดข้อมูล analog ตัวแรก)

    Parameters:
        functions_analog (list): [(func, channel, data), ...]
        functions_digital (list): [(func, data), ...]
        
    '''
    # หาจำนวนข้อมูลสูงสุดเพื่อเป็นจำนวนครั้งในการ วนลูป
    total_sample = len(functions_analog[0][2])
    # เริ่มนับเวลาครั้งแรก
    next_time = time.perf_counter()
    # วนลูปตามจำนวนของข้อมูล
    for i in range(total_sample):
        # วนสร้างสัญญาณ Analog
        for func, pin, data in functions_analog:
            func(pin, data[i])
        # วนสร้างสัญญาณ Digital
        for func, data in functions_digital:
            func(data[i])

        next_time += dt
        # Loop Busy wait + check flag Stop
        while time.perf_counter() < next_time:
            if stop_event.is_set():
                return


def analog_only(stop_event, dt, functions_analog):
    '''
    
    ส่งเฉพาะข้อมูล analog ทีละ sample

    Parameters:
        functions_analog (list): [(func, channel, data), ...]
        
    '''
    # หาจำนวนข้อมูลสูงสุดเพื่อเป็นจำนวนครั้งในการ วนลูป
    total_sample = len(functions_analog[0][2])
    next_time = time.perf_counter()
    # วนลูปตามจำนวนของข้อมูล
    for i in range(total_sample):
        # วนสร้างสัญญาณ Analog
        for func, pin, data in functions_analog:
            func(pin, data[i])

        next_time += dt
        # Loop Busy wait + check flag Stop
        while time.perf_counter() < next_time:
            if stop_event.is_set():
                return


def digital_only(stop_event, dt, functions_digital):
    '''
    
    ส่งเฉพาะข้อมูล digital ทีละ sample
    (จำนวน sample อ้างอิงจาก functions_digital[0][1] — tuple คือ (func, data))

    Parameters:
        functions_digital (list): [(func, data), ...]
        
    '''
    # หาจำนวนข้อมูลสูงสุดเพื่อเป็นจำนวนครั้งในการ วนลูป
    total_sample = len(functions_digital[0][1])
    next_time = time.perf_counter()
    # วนลูปตามจำนวนของข้อมูล
    for i in range(total_sample):
        # วนสร้างสัญญาณ Digital
        for func, data in functions_digital:
            func(data[i])

        next_time += dt
        # Loop Busy wait + check flag Stop
        while time.perf_counter() < next_time:
            if stop_event.is_set():
                return
