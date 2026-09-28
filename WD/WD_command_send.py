#   WD_command_send.py
#   รวมคำสั่ง (command) ที่ฝั่ง GUI เรียกใช้
#
#   flow ของทุกฟังก์ชัน:
#       ประกอบ dict คำสั่ง -> ส่งไป server -> รอ reply -> คืน (bool, status/error)
#
#   ตัว socket จริง ๆ อยู่ใน WD_TCP_Client

from WD_TCP_Client import connect_server, disconnect_server, send_to_server, receive_from_server

# ข้อความ error ที่ส่งกลับไปให้ GUI โชว์ตอนคำสั่งล้มเหลว
# Command Error (Client)
connect_e       = "[ERROR] Failed to Connect server."
discinnect_e    = "[ERROR] Failed to Disconnect server."
send_e          = "[ERROR] Failed to Send command to server."
poweroff_e      = "[ERROR] Failed to Poweroff"
# run_e           = "[ERROR] Failed to start signal generation."
# stop_e          = "[ERROR] Failed to stop signal generation."

# parameter_e     = "[ERROR] Invalid signal parameters."
parameter_em    = "[ERROR] Missing Signal Parameters."
# command_e       = "[ERROR] Missing signal parameters."


# =================================
# Connect
# =================================
def connect_board(host_name):
    '''
    เปิด socket ก่อน แล้วค่อยส่ง cmd "connect" ให้บอร์ดรู้ตัว

    Parameters:
        host_name (str): IP / hostname ของบอร์ด

    Returns:
        (bool, str): (True, status จากบอร์ด) ถ้าสำเร็จ
        
                     (False, connect_e) ถ้าเปิด socket ไม่ได้
                     
                     (False, send_e) ถ้าส่ง cmd ไม่ได้
    '''
    ret = connect_server(host_name)
    # เตรียม command เพื่อส่งไปที่ server
    if ret:
        message = {
            "cmd":"connect"
        }
        # เช็คว่าสามารถส่งข้อมูลได้สำเร็จไหม
        ret = send_to_server(message)
        if ret:
            reply = receive_from_server()
            return True, reply['reply']['status']
        else:
            return False, send_e
    else:
        return False, connect_e


# =================================
# Disconnect
# =================================
def disconnect_board():
    '''
    บอกบอร์ดว่าจะเลิกแล้ว (cmd "disconnect") รับ reply แล้วค่อยปิด socket ฝั่งเรา

    Returns:
        (bool, str): (True, status จากบอร์ด) ถ้าปิดเรียบร้อย
        
                     (False, send_e) ถ้าส่ง cmd ไม่ได้
                     
                     (False, discinnect_e) ถ้าปิด socket ฝั่งเราไม่สำเร็จ
    '''
    # เตรียม command เพื่อส่งไปที่ server
    message = {
        "cmd":"disconnect"
    }
    # เช็คว่าสามารถส่งข้อมูลได้สำเร็จไหม
    ret = send_to_server(message)
    if ret:
        reply = receive_from_server()
        ret = disconnect_server()
        if ret:
            return True, reply['reply']['status']
        else:
            return False, discinnect_e
    else:
        return False, send_e


# =================================
# Poweroff
# =================================
def poweroff_board():
    '''
    สั่งปิดบอร์ด (cmd "poweroff") แล้วปิด socket ตาม เหมือน disconnect แต่ดุกว่า

    Returns:
        (bool, str): (True, status จากบอร์ด) ถ้าสั่งปิดได้
        
                     (False, send_e) ถ้าส่ง cmd ไม่ได้
                     
                     (False, poweroff_e) ถ้าปิด socket ฝั่งเราไม่สำเร็จ
    '''
    # เตรียม command เพื่อส่งไปที่ server
    message = {
        "cmd":"poweroff"
    }
    # เช็คว่าสามารถส่งข้อมูลได้สำเร็จไหม
    ret = send_to_server(message)
    if ret:
        reply = receive_from_server()
        ret = disconnect_server()
        if ret:
            return True, reply['reply']['status']
        else:
            return False, poweroff_e
    else:
        return False, send_e


# =================================
# Run
# =================================
def run_signal_gen_wd(input_parameter_signal):
    '''
    สั่งบอร์ดปล่อยสัญญาณ เอา cmd "run" มารวมกับ parameter ที่รับเข้ามาแล้วส่งไปทั้งก้อน

    Parameters:
        input_parameter_signal (dict): พารามิเตอร์สัญญาณ ต้องมี key "sequence"

    Returns:
        (bool, str): (True, status จากบอร์ด) ถ้าส่งได้
        
                     (False, parameter_em) ถ้าไม่มี "sequence"
                     
                     (False, send_e) ถ้าส่ง cmd ไม่ได้
    '''
    # เช็คว่ามีข้อมูลของสัญญาณที่ต้องการส่งไหม
    if input_parameter_signal['sequence']:
        # เตรียม command เพื่อส่งไปที่ server
        message = {
            "cmd":"run"
        }
        message.update(input_parameter_signal)
        # เช็คว่าสามารถส่งข้อมูลได้สำเร็จไหม
        ret = send_to_server(message)
        if ret:
            reply = receive_from_server()
            return True, reply['reply']['status']
        else:
            return False, send_e
    else:
        return False, parameter_em


# =================================
# Stop
# =================================
def stop_signal_gen_wd():
    '''
    สั่งหยุดสัญญาณ (cmd "stop") สั้น ๆ ส่งแล้วรอ status กลับ

    Returns:
        (bool, str): (True, status จากบอร์ด) ถ้าส่งได้
        
                     (False, send_e) ถ้าส่ง cmd ไม่ได้
    '''
    # เตรียม command เพื่อส่งไปที่ server
    message = {
        "cmd":"stop"
    }
    # เช็คว่าสามารถส่งข้อมูลได้สำเร็จไหม
    ret = send_to_server(message)
    if ret:
        reply = receive_from_server()
        return True, reply['reply']["status"]
    else:
        return False, send_e


# =================================
# Ping
# =================================
def check_connection_status():
    '''
    เช็คว่าบอร์ดยังอยู่ไหม แบบ ping-pong: ส่ง "ping" ถ้าได้ "pong" กลับมาถือว่ายังต่อกันอยู่

    Returns:
        (bool, str/None): (True, status) ถ้าได้ "pong" กลับมา
        
                          (False, None) ถ้าส่งไม่ได้, ไม่มี response, หรือไม่ใช่ "pong"
    '''
    # เตรียม command เพื่อส่งไปที่ server
    message = {
        "cmd": "ping"
    }
    # เช็คว่าสามารถส่งข้อมูลได้สำเร็จไหม
    ret = send_to_server(message)

    if not ret:
        return False, None
    # รับข้อมูลที่มาจาก server
    response = receive_from_server()

    # ถ้า เป็น None แสดงว่าการเชื่อมต่อหลุดแล้ว
    if response is None:
        return False, None


    cmd = response["reply"].get("cmd")
    status = response["reply"].get("status")

    # ได้ "pong" = ยังเชื่อมต่ออยู่
    if cmd == "pong":
        return True, status

    return False, None
