import BlynkLib                     # Giúp kết nối Raspberry Pi với nền tảng Blynk
from BlynkTimer import BlynkTimer   # Giúp tạo và quản lý các bộ định thời (timer) trong Blynk
import RPi.GPIO as GPIO             # Điều khiển các chân của Raspberry Pi
import adafruit_dht                 # Sử dụng để đọc giá trị nhiệt độ độ ẩm từ DHT11
import board                        # Khai báo chân OUT sử dụng trong DHT11
import threading                    # Để thực hiện đa luồng, cho phép nhiều tác vụ chạy động thời
import time                         # Để làm việc với thời gian (ví dụ: tạo độ trễ, đo thời gian)
from gpiozero import MotionSensor   # Để sử dụng thư viện cho cảm biến chuyển động
import ssl                          # Để quản lý các kết nối an toàn SSL/TLS.

BLYNK_AUTH_TOKEN = '5Ub2kmOG16L5xtLc7X2xrCr9R3nrM0On'

# Khởi tạo các đèn tương ứng với các chân GPIO trong RPi
room_led_pin = 21           # Chân GPIO <=> đèn trong phòng
hallway_led_pin = 17        # Chân GPIO <=> đèn ngoài hành lang
temperature_led_pin = 16    # Chân GPIO <=> đèn cảnh báo nhiệt độ cao
humidity_led_pin = 12       # Chân GPIO <=> đèn cảnh báo độ ẩm cao
light_sensor_pin = 4        # Chân GPIO <=> Cảm biến ánh sáng

# Cấu hình GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(room_led_pin, GPIO.OUT)
GPIO.setup(hallway_led_pin, GPIO.OUT)
GPIO.setup(temperature_led_pin, GPIO.OUT)
GPIO.setup(humidity_led_pin, GPIO.OUT)
GPIO.setup(light_sensor_pin, GPIO.IN)

# Khai báo biến dùng cho motion_detected()
motion_timer = None             # Biến quản lý bộ hẹn giờ
manual_turn_hallway = False     # Biến kiểm tra xem có bật đèn hàng lang thủ công không
manual_turn_room = False     # Biến kiểm tra xem có bật đèn hàng lang thủ công không

# Khởi tạo cảm biến chuyển động:
motion_sensor = MotionSensor(26)

# Khởi tạo Blynk
blynk = BlynkLib.Blynk(BLYNK_AUTH_TOKEN)
timer = BlynkTimer()  # Khởi tạo BlynkTimer

# Khởi tạo cảm biến DHT11
dhtDevice = adafruit_dht.DHT11(board.D20)

# Mã màu ANSI cho các màu khác nhau
RED = '\033[91m'
GREEN = '\033[92m'
BLUE = '\033[94m'
RESET = '\033[0m'


# Điều khiển đèn trong phòng thông qua chân ảo
@blynk.on("V0")
def v0_write_handler(value):
    global manual_turn_room
    if int(value[0]) != 0:
        manual_turn_room = True
        GPIO.output(room_led_pin, GPIO.HIGH)
        print(GREEN + '---------> Đã bật đèn trong phòng!' + RESET)
    else:
        manual_turn_room = False
        GPIO.output(room_led_pin, GPIO.LOW)
        print(GREEN + '---------> Đã tắt đèn trong phòng!' + RESET)


def light_sensor_for_room():
    # Nếu bật đèn trong phòng bằng cách thủ công thì bỏ qua hàm này
    if manual_turn_room:
        return
    if GPIO.input(light_sensor_pin) == GPIO.HIGH:
        blynk.virtual_write(0, 1)
        GPIO.output(room_led_pin, GPIO.HIGH)
    else:
        blynk.virtual_write(0, 0)
        GPIO.output(room_led_pin, GPIO.LOW)


@blynk.on("V4")
def v4_write_handler(value):
    global manual_turn_hallway   # Khai báo biến kiểm tra bật đèn thủ công
    if int(value[0]) != 0:
        if motion_timer:
            motion_timer.cancel()
        manual_turn_hallway = True
        GPIO.output(hallway_led_pin, GPIO.HIGH)
        print(GREEN + '---------> Đã bật đèn hành lang!' + RESET)
    else:
        manual_turn_hallway = False
        GPIO.output(hallway_led_pin, GPIO.LOW)
        print(GREEN + '---------> Đã tắt đèn hành lang!' + RESET)


# Hàm để gửi nhiệt độ và độ ẩm tới Blynk
def send_sensor_data():
    try:
        temperature = dhtDevice.temperature
        temperature_f = (temperature * (float(9)/5)) + 32
        humidity = dhtDevice.humidity
        print(f"Nhiệt độ: {temperature}°C = {temperature_f}°F | Độ ẩm: {humidity}%")
        blynk.virtual_write(1, temperature)  # Gửi nhiệt độ tới Virtual Pin V1
        blynk.virtual_write(2, humidity)     # Gửi độ ẩm tới Virtual Pin V2
        blynk.virtual_write(3, temperature_f)     # Gửi độ ẩm tới Virtual Pin V3
    except RuntimeError as error:
        print(error.args[0])
    except Exception as error:
        print("Lỗi không mong muốn xảy ra:", error)


def warning_check():
    try:
        temperature = dhtDevice.temperature
        humidity = dhtDevice.humidity
        GPIO.output(temperature_led_pin, GPIO.LOW)
        GPIO.output(humidity_led_pin, GPIO.LOW)
        if temperature > 35:
            GPIO.output(temperature_led_pin, GPIO.HIGH)
            print("---------> Cảnh báo: !" + RED + "Nhiệt độ cao vượt ngưỡng cho phép!" + RESET)
            # Gửi thông báo với tên Event đã tạo
            blynk.log_event("high_temperature_warning", f"Cảnh báo: Nhiệt độ cao vượt mức cho phép!\n"
                                                f"Nhiệt độ hiện tại: {temperature}°C\n"
                                                f"Đã mở điều hòa thoáng khí!")
        if humidity > 90:
            GPIO.output(humidity_led_pin, GPIO.HIGH)
            print("---------> Cảnh báo: !" + RED + "Độ ẩm cao vượt ngưỡng cho phép!" + RESET)
            # Gửi thông báo với tên Event đã tạo
            blynk.log_event("high_humidity_warning", f"Cảnh báo: Độ ẩm cao vượt mức cho phép!\n"
                                                f"Độ ẩm hiện tại: {humidity}%\n"
                                                f"Đã mở máy hút ẩm!")
    except RuntimeError as error:
        print(error.args[0])
    except Exception as error:
        print("Lỗi không mong muốn xảy ra:", error)


# Hàm xử lý khi phát hiện chuyển động trên hành lang => Hành lang thông minh
def motion_detected():
    try:
        # Kiểm tra xem đèn có bât thủ công không, nếu đúng thì bỏ qua hàm
        if manual_turn_hallway:
            return
        # Khái báo biến toàn cục quản lý bộ hẹn giờ timer
        global motion_timer
        print(BLUE + "---------> Phát hiện chuyển động! Đèn hành lang bật" + RESET)
        GPIO.output(hallway_led_pin, GPIO.HIGH)
        blynk.virtual_write(4, 1)  # Gửi thông báo chuyển động tới Virtual Pin V4
        if motion_timer:
            motion_timer.cancel()
        motion_timer = threading.Timer(15, turn_off_led)
        motion_timer.start()
    except RuntimeError as error:
        print(error.args[0])
    except Exception as error:
        print("Lỗi không mong muốn xảy ra:", error)


def turn_off_led():
    GPIO.output(hallway_led_pin, GPIO.LOW)
    blynk.virtual_write(4, 0)  # Tắt thông báo chuyển động trên Virtual Pin V4
    print(BLUE + "---------> Không phát hiện chuyển động! Đèn hành lang tắt" + RESET)


# Gán các hàm cho các sự kiện của MotionSensor
motion_sensor.when_motion = motion_detected

# Cài đặt bộ định thời để gửi dữ liệu cảm biến mỗi giây
timer.set_interval(1, send_sensor_data)
timer.set_interval(1, warning_check)
timer.set_interval(1, light_sensor_for_room)


# Hàm để đồng bộ dữ liệu từ các chân ảo
@blynk.on("connected")
def blynk_connected():
    print("Raspberry Pi Connected to New Blynk")
    blynk.sync_virtual(0, 1, 2, 3, 4)


# Vòng lặp chính
while True:
    try:
        blynk.run()  # Xử lý các sự kiện Blynk
        timer.run()  # Xử lý các bộ định thời
    except ssl.SSLZeroReturnError:
        print("Kết nối TLS/SSL đã bị đóng. Đang kết nối lại...")
        # Thực hiện kết nối lại hoặc xử lý tình huống phù hợp
        blynk.connect()  # Cố gắng kết nối lại với Blynk
    except Exception as e:
        print(f"Đã xảy ra lỗi không mong muốn. Cụ thể: {e}")
        # Xử lý các lỗi khác nếu cần
