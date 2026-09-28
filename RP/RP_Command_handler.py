#   RP_Command_handler.py
#   ตัวกลางระหว่าง TCP Server กับส่วนสร้างสัญญาณ
#   รับ dict คำสั่งจาก server -> เลือกฟังก์ชันตาม "cmd" -> คืน (reply_data, control_server)
#
#   ทุก command คืน:
#       reply_data (dict)    : ข้อมูลตอบกลับ client
#       control_server (str) : บอก server ให้ทำอะไรต่อ
#                              "continue" / "disconnect" / "poweroff"
#
#   flag ระดับโมดูล (ติดตามสถานะการ generate สัญญาณข้ามหลายคำสั่ง):
#       flag_run  = 1 เมื่อสั่ง run แล้ว และยังไม่จบ / ยังไม่ถูกรับรู้ว่าจบ
#       flag_stop = 1 เมื่อผู้ใช้สั่ง stop ระหว่างที่กำลัง run

import subprocess
from RP_Control_program import run_signal_gen, stop_signal_gen, check_finish_signal_generater

flag_run = 0
flag_stop = 0


# =================================
# Dispatcher
# =================================

def process_callback(input_parameter_data):
    '''
    
    อ่าน input_parameter_data["cmd"] แล้วส่งต่อให้ฟังก์ชันที่เกี่ยวข้อง

    Parameters:
        input_parameter_data (dict): ต้องมีคีย์ "cmd"
                                     (โดยที่ cmd "run" ต้องมี "dt" และ "sequence" ด้วย)

    Returns:
        (dict, str): (reply_data, control_server)
        
    '''
    cmd = input_parameter_data["cmd"]

    if cmd == "connect":
        return connect_command()

    elif cmd == "disconnect":
        return disconnect_command()

    elif cmd == "poweroff":
        return poweroff_command()

    elif cmd == "run":
        return run_command(input_parameter_data)

    elif cmd == "stop":
        return stop_command()

    elif cmd == "ping":
        return pong()

    else:
        return error_or_no_command()


# =================================
# Connect / Disconnect / Poweroff
# =================================

def connect_command():
    '''
    
    client เริ่มต้น session

    Returns:
        (dict, str): (reply status "Connected", "continue")
        
    '''
    print("Connect")
    # สร้าง reply เพื่อตอบกลับการ connect
    reply_data = {
        "reply": {
            "status": "Connected"
        }
    }
    control_server = "continue"
    return reply_data, control_server


def disconnect_command():
    '''
    
    client ขอตัดการเชื่อมต่อ

    Returns:
        (dict, str): (reply status "Disconnected", "disconnect")
                     -> server จะปิด socket ของ client รายนี้
                     
    '''
    print("Disconnect")
    # สร้าง reply เพื่อตอบกลับการ disconnect
    reply_data = {
        "reply": {
            "status": "Disconnected"
        }
    }
    # เปลี่ยน state ของ server เป็น Disconnect
    control_server = "disconnect"
    return reply_data, control_server


def poweroff_command():
    '''
    
    client สั่งปิดเครื่อง

    Returns:
        (dict, str): (reply status "Power Off", "poweroff")
                     -> server จะหยุดทั้งหมดแล้วเรียก board_poweroff()
                     
    '''
    print("Poweroff")
    # สร้าง reply เพื่อตอบกลับการ Power off
    reply_data = {
        "reply": {
            "status": "Power Off"
        }
    }
    # เปลี่ยน state server เป็น Power off
    control_server = "poweroff"
    return reply_data, control_server


# สั่งปิดบอร์ดจริงผ่าน command ระบบ ถูกเรียกจาก TCP server หลังลูปหลักจบ
def board_poweroff():
    '''
    
    สั่งปิดบอร์ดจริงผ่านคำสั่งระบบ "poweroff"
    
    '''
    # คำสั่งของ Os ที่ทำให้ Hardware Power off
    subprocess.run(["poweroff"], check=True)


# =================================
# Run / Stop
# =================================

def run_command(input_parameter_data):
    '''
    
    เริ่ม generate สัญญาณ: ดึงเฉพาะ dt + sequence ส่งต่อให้ run_signal_gen() แล้วตั้ง flag_run

    Parameters:
        input_parameter_data (dict): ต้องมีคีย์ "dt" และ "sequence"

    Returns:
        (dict, str): (reply status = ผลจาก run_signal_gen()
                      เช่น "Running" / "Already Running" / "Calculate Error", "continue")
                      
    '''
    global flag_run

    print("Run")
    input_parameter_signal = {
        "dt": input_parameter_data["dt"],              # ระยะเวลาต่อ 1 sample (วินาที)
        "sequence": input_parameter_data["sequence"]   # รายการ pin + ข้อมูลที่จะส่งออก
    }
    # สร้าง reply เพื่อตอบกลับการ Run 
    reply_data = {
        "reply": {
            "status": run_signal_gen(input_parameter_signal)
        }
    }
    # เปลี่ยน flag run เพื่อใช้เช็คการกด stop ระหว่าง run 
    flag_run = 1

    control_server = "continue"
    return reply_data, control_server


def stop_command():
    '''
    
    หยุด generate สัญญาณ

    Returns:
        (dict, str): (reply status = ผลจาก stop_signal_gen(), "stop")

    หมายเหตุ: ถ้ากำลัง run อยู่ จะตั้ง flag_stop = 1 เพื่อให้ pong() รู้ว่า
             การหยุดมาจากผู้ใช้ ไม่ใช่สัญญาณจบเอง
             
    '''
    global flag_run, flag_stop

    print("Stop")
    reply_data = {
        "reply": {
            "status": stop_signal_gen()
        }
    }

    # เช็คสถานะว่าเป็นการกด stop ระหว่าง run ไหม
    if flag_run == 1:
        flag_stop = 1

    control_server = "continue"
    return reply_data, control_server


# =================================
# Ping (track connection + เช็คสัญญาณจบ)
# =================================
#
# client ยิง ping มาเป็นระยะ ทำให้ server มีจังหวะแจ้งกลับว่าสัญญาณ generate จบแล้ว
#
def pong():
    '''
    
    ตอบ pong และมีการเช็คสถานะการของการ generate สัญญาณ

    Returns:
        (dict, str): (reply มี cmd "pong" — อาจแนบ status "Gennerate Finish", "continue")

    หมายเหตุ: เมื่อ flag_run == 1
             - flag_stop == 1 (ผู้ใช้สั่ง stop): เคลียร์ flag ทั้งคู่ ไม่แจ้ง "จบ"
             - ไม่ได้สั่ง stop: ถ้า check_finish_signal_generater() คืน True
               แนบ status "Gennerate Finish" แล้วเคลียร์ flag_run
               
    '''
    global flag_run, flag_stop

    print("pong")
    # สร้าง reply pong เพื่อตอบกลับ สำหรับการเช็คสถานะการเชื่อมต่อ
    reply_data = {
        "reply": {
            "cmd": "pong"
        }
    }

    # ให้เพิ่ม reply ถ้าการสร้างสัญญาณนั้นสร้างเสร็จโดยไม่มีการกด stop และใช้ในการ reset flag run, stop
    if flag_run == 1:
        if flag_stop == 1:
            flag_stop = 0
            flag_run = 0
        else:
            if check_finish_signal_generater():
                status = {"status": "Gennerate Finish"}
                reply_data["reply"].update(status)

                flag_run = 0

    control_server = "continue"
    return reply_data, control_server


# =================================
# Error
# =================================

def error_or_no_command():
    '''
    
    ตอบกลับเมื่อได้คำสั่งที่ไม่รู้จัก

    Returns:
        (dict, str): (reply status "ERROR" + message "Unknown Command", "continue")
        
    '''
    reply_data = {
        "reply": {
            "status": "ERROR",
            "message": "Unknown Command"
        }
    }
    control_server = "continue"
    return reply_data, control_server
