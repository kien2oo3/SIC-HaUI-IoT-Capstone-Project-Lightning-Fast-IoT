import BlynkLib
from BlynkTimer import BlynkTimer
import ssl
import RPi.GPIO as GPIO
from gpiozero.pins.pigpio import PiGPIOFactory
from gpiozero import DistanceSensor, LED
from gpiozero.exc import DistanceSensorNoEcho
import spidev
import threading


# Khai báo hằng
BLYNK_AUTH_TOKEN = 'hjJXjzoo-x41NtPLQAn0QQWRR7eUUM4k'
TRIGGER_PIN = 13
ECHO_PIN = 19
sound_timer = None      # Biến quản lý bộ he giờ

# Đèn tín hiệu đóng mở cửa tương ứng với chân 23 GPIO:
led_pin = 23

status_led_pin = 24         # Chân GPIO <=> đèn led bật tắt chế độ bảo vệ
sound_sensor_pin = 18       # Chân GPIO <=> cảm biến âm thanh
buzzer_pin = 27             # Chân GPIO <=> còi Buzzer
fire_pin = 6                # Chân GPIO <=> cảm biến lửa
warning_fire_pin = 22       # Chân GPIO <=> đèn cảnh báo lửa
warning_gas_pin = 5         # Chân GPIO <=> đèn cảnh báo khí gas

w_led = LED(25)        # Khởi tạo đèn cảnh báo khi có âm thanh lạ sử dụng LED của gpio zero:

# Cấu hình GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Thiết lập chân
GPIO.setup(led_pin, GPIO.OUT)
GPIO.setup(status_led_pin, GPIO.OUT)
GPIO.setup(warning_gas_pin, GPIO.OUT)
GPIO.setup(warning_fire_pin, GPIO.OUT)
GPIO.setup(sound_sensor_pin, GPIO.IN)

GPIO.setup(buzzer_pin, GPIO.OUT)
GPIO.setup(fire_pin, GPIO.IN)

# Khởi tạo SPI
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1350000


# Hàm đọc giá trị từ MCP3008
def read_adc(channel):
    adc = spi.xfer2([1, (8 + channel) << 4, 0])
    data = ((adc[1] & 3) << 8) + adc[2]
    return data


# Kết nối chân AO của MQ-2 với kênh 0 trên MCP3008
mq2_channel = 0

# Khởi tạo cảm biến siêu âm:
ultrasonic = DistanceSensor(echo=ECHO_PIN, trigger=TRIGGER_PIN, pin_factory=PiGPIOFactory())

# Khởi tạo Blynk
blynk = BlynkLib.Blynk(BLYNK_AUTH_TOKEN)
timer = BlynkTimer()  # Khởi tạo BlynkTimer

# Tạo biến lưu chế độ warning được bật chưa
is_warning_mode = False

# Tạo biến cảnh báo khí ga và cảnh báo lửa => Để dùng chung 1 Buzzer
gas_warning_active = False
fire_warning_active = False

# Mã màu ANSI cho các màu khác nhau
RED = '\033[91m'
GREEN = '\033[92m'
BLUE = '\033[94m'
RESET = '\033[0m'


# Hàm kiểm tra điều kiện đóng mở cửa phòng theo khoảng cách đo được
def open_close_thedoor():
    try:
        distance = round(ultrasonic.distance*100, 3)
        blynk.virtual_write(0, distance)
        print(f"Khoảng cách đến cửa phòng: {distance} cm")
        if distance <= 20:
            blynk.virtual_write(1, 1)
            GPIO.output(led_pin, GPIO.HIGH)
            print(GREEN + "--------> Đã mở cửa phòng!" + RESET)
        else:
            blynk.virtual_write(1, 0)
            GPIO.output(led_pin, GPIO.LOW)
    except RuntimeError as error:
        print(error.args[0])
    except DistanceSensorNoEcho:
        print("Không nhận được tín hiệu phản hồi từ cảm biến siêu âm.")
        distance = -1  # Gán một giá trị không hợp lệ nếu không nhận được tín hiệu
    except Exception as error:
        print("Lỗi không mong muốn xảy ra:", error)


def turn_off_warning_led():
    w_led.off()


def sound_warning_mode():
    try:
        global sound_timer
        # Nếu chưa bật cảnh báo thì bỏ qua
        if not is_warning_mode:
            return
        if GPIO.input(sound_sensor_pin) == GPIO.HIGH:
            print(RED + "--------> Cảnh báo: Có âm thanh lạ trong phòng!" + RESET)
            blynk.log_event("sound_warning", "Cảnh báo: Có âm thanh lạ trong phòng!")
            w_led.blink(on_time=0.5, off_time=0.5)
            if sound_timer:
                sound_timer.cancel()
            sound_timer = threading.Timer(5, turn_off_warning_led)
            sound_timer.start()
    except RuntimeError as error:
        print(error.args[0])
    except Exception as error:
        print("Lỗi không mong muốn xảy ra:", error)


def fire_warning_mode():
    try:
        global fire_warning_active
        # Nếu chưa bật cảnh báo thì bỏ qua
        # if not is_warning_mode:
        #     return
        if GPIO.input(fire_pin) == GPIO.LOW:
            fire_warning_active = True
            print(RED + "--------> Cảnh báo: Có lửa trong nhà!" + RESET)
            blynk.log_event("fire_warning", "Cảnh báo: Có lửa trong nhà!")
            blynk.virtual_write(3, 1)
            GPIO.output(warning_fire_pin, GPIO.HIGH)
        else:
            fire_warning_active = False
            blynk.virtual_write(3, 0)
            GPIO.output(warning_fire_pin, GPIO.LOW)
        turn_on_off_buzzer()
    except RuntimeError as error:
        print(error.args[0])
    except Exception as error:
        print("Lỗi không mong muốn xảy ra:", error)


# Hàm ghi giá trị khi gas:
def get_gas_value():
    try:
        global gas_warning_active
        gas_value = read_adc(mq2_channel)
        blynk.virtual_write(4, gas_value)
        print(f"Giá trị khí gas hiện tại: {gas_value}")
        if gas_value > 500:
            gas_warning_active = True
            print(RED + "--------> Nguy hiểm: Khí gas vượt mức an toàn!" + RESET)
            blynk.log_event("gas_warning", f"Cảnh báo: Khí gas vượt mức an toàn!\nGiá trị khí gas= {gas_value}\nĐã mở cửa thoáng khí!")
            GPIO.output(warning_gas_pin, GPIO.HIGH)
        else:
            gas_warning_active = False
            GPIO.output(buzzer_pin, GPIO.LOW)
            GPIO.output(warning_gas_pin, GPIO.LOW)
        turn_on_off_buzzer()
    except RuntimeError as error:
        print(error.args[0])
    except Exception as error:
        print("Lỗi không mong muốn xảy ra:", error)


# Hàm bật tắt Buzzer
def turn_on_off_buzzer():
    try:
        if gas_warning_active or fire_warning_active:
            GPIO.output(buzzer_pin, GPIO.HIGH)
        else:
            GPIO.output(buzzer_pin, GPIO.LOW)
    except RuntimeError as error:
        print(error.args[0])
    except Exception as error:
        print("Lỗi không mong muốn xảy ra:", error)


# Điều khiển led qua chân ảo:
@blynk.on("V2")
def v2_write_handler(value):
    global is_warning_mode
    if int(value[0]) != 0:
        is_warning_mode = True
        GPIO.output(status_led_pin, GPIO.HIGH)
        print(GREEN + '--------> Đã bật chế độ cảnh báo!' + RESET)
        if sound_timer:
            sound_timer.cancel()
    else:
        is_warning_mode = False
        GPIO.output(status_led_pin, GPIO.LOW)
        w_led.off()
        print(GREEN + "--------> Đã tắt chế độ cảnh báo!" + RESET)


# Cài đặt bộ định thời để gửi dữ liệu cảm biến mỗi giây => Gọi lại hàm sau  mỗi giây
timer.set_interval(1, open_close_thedoor)
timer.set_interval(1, fire_warning_mode)
timer.set_interval(1, get_gas_value)
timer.set_interval(1, sound_warning_mode)


# Hàm để đồng bộ dữ liệu từ các chân ảo
@blynk.on("connected")
def blynk_connected():
    print("Raspberry Pi Connected to New Blynk")
    # Đồng bộ trạng thái của chân ảo V1, V2, V3
    blynk.sync_virtual(0, 1, 2, 3, 4)


# Vòng lặp chính
while True:
    try:
        blynk.run()  # Xử lý các sự kiện Blynk
        timer.run()  # Xử lý các bộ định thời
    except ssl.SSLZeroReturnError:
        # Thực hiện kết nối lại hoặc xử lý tình huống phù hợp
        print("Kết nối TLS/SSL đã bị đóng. Đang kết nối lại...")
        blynk.connect()  # Cố gắng kết nối lại với Blynk
    except Exception as e:
        # Xử lý các lỗi khác nếu cần
        print(f"Đã xảy ra lỗi không mong muốn. Cụ thể: {e}")
