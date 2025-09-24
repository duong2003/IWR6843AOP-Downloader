#!/usr/bin/env python3
"""
IWR6843AOP Break Signal Test - Simple Version
============================================
Test BREAK signal and ACK response from IWR6843AOP

Steps:
1. Open COM9
2. Send BREAK signal  
3. Listen for ACK (0xCC)
4. Report result

Usage: python break_test.py
"""

import sys
import time
import serial

def test_break_signal():
    """Simple break signal test"""
    print("IWR6843AOP Break Signal Test")
    print("=" * 30)
    
    # Step 1: Open COM port
    print("1. Opening COM9...")
    try:
        ser = serial.Serial('COM16', 115200, timeout=3)
        print("   ✓ COM16 opened")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # Step 2: Send BREAK signal
    print("2. Sending BREAK signal...")
    try:
        ser.break_condition = True
        time.sleep(0.1)  # 100ms break
        ser.break_condition = False
        print("   ✓ BREAK sent")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        ser.close()
        return False
    
    # Step 3: Listen for ACK
    print("3. Waiting for ACK (0xCC)...")
    try:
        start_time = time.time()
        while time.time() - start_time < 5:  # 5 second timeout
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                print(f"   Received: {' '.join(f'0x{b:02X}' for b in data)}")
                
                # Check for ACK
                for byte in data:
                    if byte == 0xCC:
                        print("   ✓ ACK (0xCC) received!")
                        ser.close()
                        return True
            time.sleep(0.01)
        
        print("   ✗ No ACK received")
        ser.close()
        return False
        
    except Exception as e:
        print(f"   ✗ Error: {e}")
        ser.close()
        return False

def main():
    print("Put IWR6843AOP in bootloader mode first!")
    print("(Hold BOOT, press RESET, release BOOT)")
    input("Press Enter to start test...")
    print()
    
    success = test_break_signal()
    
    print()
    if success:
        print("🎉 SUCCESS! Device is in bootloader mode")
    else:
        print("❌ FAILED! Check:")
        print("  - Device in bootloader mode?")
        print("  - COM9 connected?")
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()