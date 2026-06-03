from sorter.adapters.hardware.marlin_motion import MarlinMotionAdapter
from sorter.adapters.hardware.marlin_transport import MarlinSerialTransport
from sorter.adapters.hardware.picamera2_camera import PiCamera2Adapter
from sorter.adapters.hardware.gpio_vacuum import GpioVacuumAdapter
from sorter.adapters.hardware.neopixel_lights import NeoPixelLightsAdapter


def main() -> int:
    transport = MarlinSerialTransport()
    motion = MarlinMotionAdapter(transport=transport)
    camera = PiCamera2Adapter()
    vacuum = GpioVacuumAdapter()
    lights = NeoPixelLightsAdapter(transport=transport)

    try:
        motion.home_axes()
        motion.move_xy(10, 10)
        motion.move_z(5)
        frame = camera.capture_frame()
        vacuum.on()
        vacuum.off()
        lights.set_status("running")

        print({
            "pose": motion.get_pose(),
            "frame": frame.frame_id,
            "vacuum": vacuum.is_on(),
            "lights_cmd": lights.last_command,
            "marlin_commands": transport.command_log,
            "board": "BTT SKR 1.4 Turbo (neopixel via Marlin M150)",
        })
        return 0
    finally:
        transport.close()


if __name__ == "__main__":
    raise SystemExit(main())
