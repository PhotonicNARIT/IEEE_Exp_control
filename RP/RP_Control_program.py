#   RP_Control_program.py
#   ชั้นควบคุมตัวสร้างสัญญาณ (state machine + จัดการ thread)
#
#   current_state : "STOP" = ว่าง / "RUN" = มี thread กำลัง generate สัญญาณ
#   การ generate รันบน thread แยกเพื่อไม่บล็อก TCP Server สั่งหยุดผ่าน stop_event
#   previous_state : ใช้จับขอบ RUN -> STOP เพื่อบอกว่าสัญญาณเพิ่ง generate เสร็จ

import threading
from RP_Create_signal import calculate_signal_setting, send_signal_to_pinout

current_state  = "STOP"
previous_state = "STOP"


signal_thread = None                  # thread ที่รัน generate สัญญาณ
stop_event    = threading.Event()     # flag สั่งหยุด thread
state_lock    = threading.Lock()      # กันการแก้ state พร้อมกันจากหลาย thread


# =================================
# Run / Stop
# =================================

def run_signal_gen(input_parameter_signal):
    '''
    เริ่ม generate สัญญาณ (เฉพาะตอน current_state == "STOP")

    ขั้นตอน: calculate_signal_setting() -> สร้าง + start thread (_run_and_cleanup)
             -> current_state = "RUN"

    Parameters:
        input_parameter_signal (dict): มีคีย์ "dt" และ "sequence"

    Returns:
        str: "Running"         - เริ่มสำเร็จ
             "Already Running"  - มีสัญญาณกำลังออกอยู่แล้ว
             "Calculate Error"  - calculate_signal_setting เจอ pin ที่ไม่รู้จัก
             
    '''
    global current_state, signal_thread
    with state_lock:
        # เช็คว่าตอนนี้ไม่มีการสร้างสัญญาณค้างอยู่
        if current_state == "STOP":
            # ส่งค่า input parameter signal เพื่อเข้าไปเช็คความถูกต้องแล้ว แยกส่วนของข้อมูล
            ret, dt, func_analog, func_digital = calculate_signal_setting(input_parameter_signal)
            if ret:
                stop_event.clear()   # เคลียร์ flag stop จากรอบก่อน
                signal_thread = threading.Thread(
                    target=_run_and_cleanup,
                    args=(stop_event, dt, func_analog, func_digital)
                )
                current_state = "RUN"
                signal_thread.start()

            else:
                return "Calculate Error"

        else:
            return "Already Running"

        return "Running"


def stop_signal_gen():
    '''
    สั่งหยุด thread ที่กำลัง generate อยู่ แล้วรอจน thread จบจริง

    Returns:
        str: "Signal generator stopped" - หยุดสำเร็จ
             "Already stopped"           - ไม่มีสัญญาณกำลังออกอยู่แล้ว
    '''
    global current_state, signal_thread

    with state_lock:
        # เช็คตอนนี้มีสัญญาณถูกสร้างอยู่ไหม
        if current_state != "RUN":
            return "Already stopped"
        stop_event.set()   # สั่งให้ loop ใน thread ออกจากการทำงาน

    if signal_thread is not None:
        signal_thread.join()

    return "Signal generator stopped"


# =================================
# Thread wrapper / เช็คสัญญาณจบ
# =================================

# ตัวห่อที่รันในเธรด: เรียกงาน generate จริง แล้ว reset state ไม่ว่าจะจบแบบไหน
def _run_and_cleanup(stop_event, dt, func_analog, func_digital):
    '''
    เรียก send_signal_to_pinout() แล้วตั้ง current_state = "STOP" เสมอ
    (ทั้งจบปกติ / ถูกสั่งหยุด / มี exception)

    Parameters:
        stop_event (threading.Event): ธงสั่งหยุด
        dt (float): ระยะเวลาต่อ 1 sample (วินาที)
        func_analog (list): [(ฟังก์ชัน, channel, data), ...]
        func_digital (list): [(ฟังก์ชัน, data), ...]
    '''
    global current_state
    try:
        send_signal_to_pinout(stop_event, dt, func_analog, func_digital)
    except Exception as e:
        print(f"[signal_gen] error: {e}")
    finally:
        with state_lock:
            current_state = "STOP"


def check_finish_signal_generater():
    '''
    เช็คว่าสัญญาณเพิ่ง generate เสร็จหรือยัง (edge detection RUN -> STOP)

    Returns:
        bool: True เพียงครั้งเดียว ณ จังหวะที่สถานะเปลี่ยนจาก RUN เป็น STOP
              (หลังจากนั้นอัปเดต previous_state จึงไม่แจ้งซ้ำ)
    '''
    global previous_state

    with state_lock:
        # หากสัญญาณเปลี่ยนจาก Run -> Stop หมายถึงสัญญาณถูกสร้างเสร็จแล้ว
        state_changed = (
            previous_state == "RUN"
            and current_state == "STOP"
        )

        previous_state = current_state

    return state_changed
