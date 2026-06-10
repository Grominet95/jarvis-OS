#ifndef USER_USB_RAM
#error USER_USB_RAM
#endif

#include "generated/keypad_config.h"
#include "generated/keypad_led_profile.h"
#include "generated/keypad_keys_profile.h"
#include "src/userUsbHidKeyboard/USBHIDKeyboard.h"

#define K1_PIN 33
#define K2_PIN 11
#define KEY_LED_PIN 34
#define EDGE_LED_PIN 30
#define KEY_LED_MASK 0x10
#define EDGE_LED_MASK 0x01
#define KEY_DIM 64
#define LED_BOOT_TEST_MS 240
#define EDGE_RGBW 0
#define EDGE_MASTER_DIM 128
#define KEY_MASTER_DIM 180
#define ANIM_FRAME_MS 28

#define LED_NOP() __asm nop __endasm

#if KEYPAD_SOFTWARE_RAPID_TRIGGER
#define KEYPAD_RT_RESET_TICKS (((KEYPAD_RT_RESET_MS) + (KEYPAD_RT_POLL_MS)-1) / (KEYPAD_RT_POLL_MS))
#endif

static bool key1State = false;
static bool key2State = false;
static uint16_t animFrame = 0;
static uint16_t lastAnimMs = 0;
static uint8_t keyAnim[KEYPAD_KEY_LED_COUNT * 3];
static uint8_t edgeAnim[KEYPAD_EDGE_LED_COUNT * 3];

static inline void led_line_high(uint8_t mask) {
  P3 |= mask;
}

static inline void led_line_low(uint8_t mask) {
  P3 &= ~mask;
}

static inline void led_send_bit_1(uint8_t mask) {
  led_line_high(mask);
  LED_NOP(); LED_NOP(); LED_NOP(); LED_NOP(); LED_NOP(); LED_NOP(); LED_NOP(); LED_NOP();
  led_line_low(mask);
  LED_NOP(); LED_NOP(); LED_NOP(); LED_NOP();
}

static inline void led_send_bit_0(uint8_t mask) {
  led_line_high(mask);
  LED_NOP(); LED_NOP();
  led_line_low(mask);
  LED_NOP(); LED_NOP(); LED_NOP(); LED_NOP(); LED_NOP(); LED_NOP(); LED_NOP(); LED_NOP();
  LED_NOP(); LED_NOP();
}

static void led_send_byte(uint8_t mask, uint8_t value) {
  for (uint8_t i = 0; i < 8; i++) {
    if (value & 0x80) {
      led_send_bit_1(mask);
    } else {
      led_send_bit_0(mask);
    }
    value <<= 1;
  }
}

static void led_send_rgb(uint8_t mask, uint8_t r, uint8_t g, uint8_t b) {
  led_send_byte(mask, g);
  led_send_byte(mask, r);
  led_send_byte(mask, b);
}

static void led_send_rgbw(uint8_t mask, uint8_t r, uint8_t g, uint8_t b, uint8_t w) {
  led_send_byte(mask, g);
  led_send_byte(mask, r);
  led_send_byte(mask, b);
  led_send_byte(mask, w);
}

static uint8_t scale8(uint8_t v, uint8_t factor) {
  return (uint16_t)v * (uint16_t)factor / 255;
}

static uint8_t absDiff8(uint8_t a, uint8_t b) {
  return a > b ? (a - b) : (b - a);
}

static void wheel(uint8_t pos, uint8_t *r, uint8_t *g, uint8_t *b) {
  uint8_t p = 255 - pos;
  if (p < 85) {
    *r = 255 - p * 3;
    *g = 0;
    *b = p * 3;
    return;
  }
  if (p < 170) {
    p -= 85;
    *r = 0;
    *g = p * 3;
    *b = 255 - p * 3;
    return;
  }
  p -= 170;
  *r = p * 3;
  *g = 255 - p * 3;
  *b = 0;
}

static uint8_t pseudo8(uint16_t n) {
  uint16_t x = (n * 2053u + 13849u) ^ (n >> 3);
  return (uint8_t)(x & 0xFF);
}

static uint8_t rgb_max8(uint8_t r, uint8_t g, uint8_t b) {
  uint8_t m = r > g ? r : g;
  return b > m ? b : m;
}

static uint8_t rgb_min8(uint8_t r, uint8_t g, uint8_t b) {
  uint8_t m = r < g ? r : g;
  return b < m ? b : m;
}

static void rgb_to_hsv(uint8_t r, uint8_t g, uint8_t b, uint8_t *h, uint8_t *s, uint8_t *v) {
  uint8_t maxc = rgb_max8(r, g, b);
  uint8_t minc = rgb_min8(r, g, b);
  *v = maxc;
  uint8_t d = maxc - minc;
  if (maxc < 6 || d < 6) {
    *h = 0;
    *s = 0;
    return;
  }
  *s = (uint16_t)d * 255 / maxc;
  int16_t hh;
  if (maxc == r) {
    hh = (int16_t)(((int32_t)g - (int32_t)b) * 43 / (int32_t)d);
  } else if (maxc == g) {
    hh = 85 + (int16_t)(((int32_t)b - (int32_t)r) * 43 / (int32_t)d);
  } else {
    hh = 170 + (int16_t)(((int32_t)r - (int32_t)g) * 43 / (int32_t)d);
  }
  if (hh < 0) {
    hh += 256;
  }
  if (hh > 255) {
    hh -= 256;
  }
  *h = (uint8_t)hh;
}

static void hsv_to_rgb(uint8_t h, uint8_t s, uint8_t v, uint8_t *r, uint8_t *g, uint8_t *b) {
  if (s == 0) {
    *r = v;
    *g = v;
    *b = v;
    return;
  }
  uint8_t region = h / 43;
  uint8_t rem = (h - (uint16_t)region * 43) * 6;
  uint8_t p = (uint16_t)v * (255 - s) / 255;
  uint8_t q = (uint16_t)v * (255 - (uint16_t)s * rem / 255) / 255;
  uint8_t t = (uint16_t)v * (255 - (uint16_t)s * (255 - rem) / 255) / 255;
  switch (region) {
    case 0:
      *r = v;
      *g = t;
      *b = p;
      break;
    case 1:
      *r = q;
      *g = v;
      *b = p;
      break;
    case 2:
      *r = p;
      *g = v;
      *b = t;
      break;
    case 3:
      *r = p;
      *g = q;
      *b = v;
      break;
    case 4:
      *r = t;
      *g = p;
      *b = v;
      break;
    default:
      *r = v;
      *g = p;
      *b = q;
      break;
  }
}

static uint8_t hue_add_clamp(uint8_t base, int16_t delta) {
  int16_t x = (int16_t)base + delta;
  while (x < 0) {
    x += 256;
  }
  while (x > 255) {
    x -= 256;
  }
  return (uint8_t)x;
}

static uint8_t smoothstep8_u8(uint8_t t) {
  uint32_t x = t;
  uint32_t x2 = x * x / 255;
  uint32_t x3 = x2 * x / 255;
  uint32_t s = 3 * x2 - 2 * x3;
  if (s > 255) {
    return 255;
  }
  return (uint8_t)s;
}

static void animate_buffers() {
  uint16_t edgeRate = 2u + ((uint16_t)KEYPAD_EDGE_SPEED8 * 34u / 255u);
  uint32_t phase32 = (uint32_t)animFrame * (uint32_t)edgeRate;
  uint16_t phaseE = (uint16_t)phase32;
  uint8_t i;

  for (i = 0; i < KEYPAD_KEY_LED_COUNT * 3; i++) keyAnim[i] = KEYPAD_KEY_LED_RGB[i];
  for (i = 0; i < KEYPAD_EDGE_LED_COUNT * 3; i++) edgeAnim[i] = KEYPAD_EDGE_LED_RGB[i];

  if (KEYPAD_EFFECT_ID == 1) {
    uint8_t p = (uint8_t)phaseE;
    uint8_t tri = p < 128 ? (p << 1) : ((255 - p) << 1);
    if (tri > 254) {
      tri = 254;
    }
    uint8_t ampE = 95 + scale8(smoothstep8_u8(tri), 160);
    uint8_t he, se, ve, r, g, b;
    for (i = 0; i < KEYPAD_EDGE_LED_COUNT; i++) {
      uint8_t bi = i * 3;
      rgb_to_hsv(KEYPAD_EDGE_LED_RGB[bi + 0], KEYPAD_EDGE_LED_RGB[bi + 1], KEYPAD_EDGE_LED_RGB[bi + 2], &he, &se, &ve);
      ve = scale8(ve, ampE);
      hsv_to_rgb(he, se, ve, &r, &g, &b);
      edgeAnim[bi + 0] = r;
      edgeAnim[bi + 1] = g;
      edgeAnim[bi + 2] = b;
    }
  } else if (KEYPAD_EFFECT_ID == 2) {
    uint8_t r, g, b;
    for (i = 0; i < KEYPAD_EDGE_LED_COUNT; i++) {
      wheel((uint8_t)((uint16_t)phaseE + (uint16_t)i * 255u / KEYPAD_EDGE_LED_COUNT), &r, &g, &b);
      edgeAnim[i * 3 + 0] = r;
      edgeAnim[i * 3 + 1] = g;
      edgeAnim[i * 3 + 2] = b;
    }
  } else if (KEYPAD_EFFECT_ID == 3 || KEYPAD_EFFECT_ID == 4) {
    uint32_t circum = (uint32_t)KEYPAD_EDGE_LED_COUNT << 8;
    uint16_t stepP = 2u + ((uint16_t)KEYPAD_EDGE_SPEED8 * 28u / 255u);
    if (stepP < 2) {
      stepP = 2;
    }
    uint32_t head_u = ((uint32_t)animFrame * stepP) % circum;
    uint16_t half = (uint16_t)KEYPAD_EDGE_LED_COUNT << 7;
    uint16_t width = (KEYPAD_EFFECT_ID == 3) ? 520 : 340;
    for (i = 0; i < KEYPAD_EDGE_LED_COUNT; i++) {
      uint16_t pos_i = (uint16_t)i << 8;
      int16_t dh = (int16_t)head_u - (int16_t)pos_i;
      if (dh > (int16_t)half) {
        dh -= (int16_t)KEYPAD_EDGE_LED_COUNT << 8;
      } else if (dh < -(int16_t)half) {
        dh += (int16_t)KEYPAD_EDGE_LED_COUNT << 8;
      }
      uint16_t ad = dh < 0 ? (uint16_t)(-dh) : (uint16_t)dh;
      uint8_t glow;
      if (ad >= width) {
        glow = 52;
      } else {
        glow = (uint8_t)(255 - (uint16_t)ad * 203 / width);
      }
      uint8_t bi = i * 3;
      uint8_t he, se, ve, r, g, b;
      rgb_to_hsv(KEYPAD_EDGE_LED_RGB[bi + 0], KEYPAD_EDGE_LED_RGB[bi + 1], KEYPAD_EDGE_LED_RGB[bi + 2], &he, &se, &ve);
      ve = scale8(ve, glow);
      hsv_to_rgb(he, se, ve, &r, &g, &b);
      edgeAnim[bi + 0] = r;
      edgeAnim[bi + 1] = g;
      edgeAnim[bi + 2] = b;
    }
  } else if (KEYPAD_EFFECT_ID == 5) {
    uint8_t ph = (uint8_t)(phaseE >> 1);
    for (i = 0; i < KEYPAD_EDGE_LED_COUNT; i++) {
      uint8_t u = (uint8_t)((uint16_t)i * 255u / KEYPAD_EDGE_LED_COUNT + ph);
      uint8_t tri = u < 128 ? (u << 1) : ((255 - u) << 1);
      if (tri > 254) {
        tri = 254;
      }
      uint8_t br = smoothstep8_u8(tri);
      uint8_t bi = i * 3;
      uint8_t he, se, ve, r, g, b;
      rgb_to_hsv(KEYPAD_EDGE_LED_RGB[bi + 0], KEYPAD_EDGE_LED_RGB[bi + 1], KEYPAD_EDGE_LED_RGB[bi + 2], &he, &se, &ve);
      ve = scale8(ve, 58 + scale8(br, 197));
      hsv_to_rgb(he, se, ve, &r, &g, &b);
      edgeAnim[bi + 0] = r;
      edgeAnim[bi + 1] = g;
      edgeAnim[bi + 2] = b;
    }
  } else if (KEYPAD_EFFECT_ID == 6) {
    for (i = 0; i < KEYPAD_EDGE_LED_COUNT; i++) {
      uint8_t n = pseudo8((uint16_t)animFrame * 7u + i * 37u);
      uint8_t bi = i * 3;
      uint8_t he, se, ve, r, g, b;
      rgb_to_hsv(KEYPAD_EDGE_LED_RGB[bi + 0], KEYPAD_EDGE_LED_RGB[bi + 1], KEYPAD_EDGE_LED_RGB[bi + 2], &he, &se, &ve);
      int16_t jit = (int16_t)(n & 3u) - 1;
      he = hue_add_clamp(he, jit);
      uint8_t amp = 78 + scale8((uint8_t)(((uint16_t)n * (uint16_t)n) >> 8), 162);
      ve = scale8(ve, amp);
      hsv_to_rgb(he, se, ve, &r, &g, &b);
      edgeAnim[bi + 0] = r;
      edgeAnim[bi + 1] = g;
      edgeAnim[bi + 2] = b;
    }
  }

  if (!key1State) {
    keyAnim[0] = scale8(keyAnim[0], KEY_DIM);
    keyAnim[1] = scale8(keyAnim[1], KEY_DIM);
    keyAnim[2] = scale8(keyAnim[2], KEY_DIM);
  }
  if (!key2State) {
    keyAnim[3] = scale8(keyAnim[3], KEY_DIM);
    keyAnim[4] = scale8(keyAnim[4], KEY_DIM);
    keyAnim[5] = scale8(keyAnim[5], KEY_DIM);
  }

  for (i = 0; i < KEYPAD_KEY_LED_COUNT * 3; i++) {
    keyAnim[i] = scale8(keyAnim[i], KEY_MASTER_DIM);
  }
  for (i = 0; i < KEYPAD_EDGE_LED_COUNT * 3; i++) {
    edgeAnim[i] = scale8(edgeAnim[i], EDGE_MASTER_DIM);
  }
}

static void key_leds_flush(bool k1Down, bool k2Down) {
  noInterrupts();
  (void)k1Down;
  (void)k2Down;
  led_send_rgb(KEY_LED_MASK, keyAnim[0], keyAnim[1], keyAnim[2]);
  led_send_rgb(KEY_LED_MASK, keyAnim[3], keyAnim[4], keyAnim[5]);
  interrupts();
  delayMicroseconds(90);
}

static void edge_leds_flush() {
  noInterrupts();
  for (uint8_t i = 0; i < KEYPAD_EDGE_LED_COUNT; i++) {
    uint8_t base = i * 3;
#if EDGE_RGBW
    led_send_rgbw(
      EDGE_LED_MASK,
      edgeAnim[base + 0],
      edgeAnim[base + 1],
      edgeAnim[base + 2],
      0
    );
#else
    led_send_rgb(
      EDGE_LED_MASK,
      edgeAnim[base + 0],
      edgeAnim[base + 1],
      edgeAnim[base + 2]
    );
#endif
  }
  interrupts();
  delayMicroseconds(90);
}

static void leds_flush_all() {
  animate_buffers();
  key_leds_flush(key1State, key2State);
  edge_leds_flush();
}

static void key_leds_raw(uint8_t r0, uint8_t g0, uint8_t b0, uint8_t r1, uint8_t g1, uint8_t b1) {
  noInterrupts();
  led_send_rgb(KEY_LED_MASK, r0, g0, b0);
  led_send_rgb(KEY_LED_MASK, r1, g1, b1);
  interrupts();
  delayMicroseconds(120);
}

static void edge_leds_raw(uint8_t r, uint8_t g, uint8_t b) {
  noInterrupts();
  for (uint8_t i = 0; i < KEYPAD_EDGE_LED_COUNT; i++) {
#if EDGE_RGBW
    led_send_rgbw(EDGE_LED_MASK, r, g, b, 0);
#else
    led_send_rgb(EDGE_LED_MASK, r, g, b);
#endif
  }
  interrupts();
  delayMicroseconds(120);
}

static uint8_t map_fr_azerty_for_hid(uint8_t c) {
#if KEYBOARD_LAYOUT_FR_AZERTY
  switch (c) {
  case 'a':
    return 'q';
  case 'A':
    return 'Q';
  case 'q':
    return 'a';
  case 'Q':
    return 'A';
  case 'z':
    return 'w';
  case 'Z':
    return 'W';
  case 'w':
    return 'z';
  case 'W':
    return 'Z';
  default:
    return c;
  }
#else
  return c;
#endif
}

static void keymods_set(uint8_t mods, bool down) {
  if (mods & 1) {
    if (down) Keyboard_press(KEY_LEFT_CTRL); else Keyboard_release(KEY_LEFT_CTRL);
  }
  if (mods & 2) {
    if (down) Keyboard_press(KEY_LEFT_SHIFT); else Keyboard_release(KEY_LEFT_SHIFT);
  }
  if (mods & 4) {
    if (down) Keyboard_press(KEY_LEFT_ALT); else Keyboard_release(KEY_LEFT_ALT);
  }
  if (mods & 8) {
    if (down) Keyboard_press(KEY_LEFT_GUI); else Keyboard_release(KEY_LEFT_GUI);
  }
}

static void keychord_set(uint8_t mods, uint8_t key, bool down) {
  uint8_t k = map_fr_azerty_for_hid(key);
  if (down) {
    keymods_set(mods, true);
    Keyboard_press(k);
  } else {
    Keyboard_release(k);
    keymods_set(mods, false);
  }
}

static void macro_type_text(const char *text) {
  uint8_t i = 0;
  while (text[i] != 0) {
    Keyboard_write(map_fr_azerty_for_hid((uint8_t)text[i]));
    i++;
  }
}

static void macro_run(uint8_t mods, uint8_t key, uint16_t delayMs, const char *text, uint8_t tapEnter) {
  Keyboard_releaseAll();
  keymods_set(mods, true);
  Keyboard_press(map_fr_azerty_for_hid(key));
  delay(14);
  Keyboard_release(map_fr_azerty_for_hid(key));
  keymods_set(mods, false);
  if (delayMs > 0) {
    delay(delayMs);
  }
  macro_type_text(text);
  if (tapEnter) {
    Keyboard_write(KEY_RETURN);
  }
}

void setup() {
  USBInit();
  pinMode(K1_PIN, INPUT_PULLUP);
  pinMode(K2_PIN, INPUT_PULLUP);
  pinMode(KEY_LED_PIN, OUTPUT);
  pinMode(EDGE_LED_PIN, OUTPUT);
  digitalWrite(KEY_LED_PIN, LOW);
  digitalWrite(EDGE_LED_PIN, LOW);
  key_leds_raw(0, 0, 0, 0, 0, 0);
  edge_leds_raw(0, 0, 0);
  key_leds_raw(
    KEYPAD_KEY_LED_RGB[0],
    KEYPAD_KEY_LED_RGB[1],
    KEYPAD_KEY_LED_RGB[2],
    KEYPAD_KEY_LED_RGB[3],
    KEYPAD_KEY_LED_RGB[4],
    KEYPAD_KEY_LED_RGB[5]
  );
  edge_leds_raw(KEYPAD_EDGE_LED_RGB[0], KEYPAD_EDGE_LED_RGB[1], KEYPAD_EDGE_LED_RGB[2]);
  delay(LED_BOOT_TEST_MS);
  leds_flush_all();
}

#if KEYPAD_SOFTWARE_RAPID_TRIGGER
static uint8_t k1Post = 0;
static uint8_t k2Post = 0;
static bool k1On = false;
static bool k2On = false;
#endif

#if !KEYPAD_SOFTWARE_RAPID_TRIGGER
static bool k1Prev = false;
static bool k2Prev = false;
#endif

void loop() {
  uint16_t nowMs = millis();
  if ((uint16_t)(nowMs - lastAnimMs) >= ANIM_FRAME_MS) {
    lastAnimMs = nowMs;
    animFrame++;
    leds_flush_all();
  }
#if KEYPAD_SOFTWARE_RAPID_TRIGGER
  delay(KEYPAD_RT_POLL_MS);
  bool r1 = !digitalRead(K1_PIN);
  if (k1Post > 0) {
    if (!r1) {
      k1Post--;
    }
    if (r1) {
      r1 = false;
    }
  }
  if (k1On != r1) {
    k1On = r1;
    key1State = r1;
    key_leds_flush(key1State, key2State);
    if (r1) {
#if KEYPAD_K1_MODE == 1
      macro_run(KEYPAD_K1_MODS, KEYPAD_K1_KEY, KEYPAD_K1_MACRO_DELAY_MS, KEYPAD_K1_MACRO_TEXT, KEYPAD_K1_MACRO_ENTER);
#else
      keychord_set(KEYPAD_K1_MODS, KEYPAD_K1_KEY, true);
#endif
    } else {
#if KEYPAD_K1_MODE == 0
      keychord_set(KEYPAD_K1_MODS, KEYPAD_K1_KEY, false);
#endif
      k1Post = KEYPAD_RT_RESET_TICKS;
    }
  }

  bool r2 = !digitalRead(K2_PIN);
  if (k2Post > 0) {
    if (!r2) {
      k2Post--;
    }
    if (r2) {
      r2 = false;
    }
  }
  if (k2On != r2) {
    k2On = r2;
    key2State = r2;
    key_leds_flush(key1State, key2State);
    if (r2) {
#if KEYPAD_K2_MODE == 1
      macro_run(KEYPAD_K2_MODS, KEYPAD_K2_KEY, KEYPAD_K2_MACRO_DELAY_MS, KEYPAD_K2_MACRO_TEXT, KEYPAD_K2_MACRO_ENTER);
#else
      keychord_set(KEYPAD_K2_MODS, KEYPAD_K2_KEY, true);
#endif
    } else {
#if KEYPAD_K2_MODE == 0
      keychord_set(KEYPAD_K2_MODS, KEYPAD_K2_KEY, false);
#endif
      k2Post = KEYPAD_RT_RESET_TICKS;
    }
  }
#else
  bool k1 = !digitalRead(K1_PIN);
  if (k1Prev != k1) {
    k1Prev = k1;
    key1State = k1;
    key_leds_flush(key1State, key2State);
    if (k1) {
#if KEYPAD_K1_MODE == 1
      macro_run(KEYPAD_K1_MODS, KEYPAD_K1_KEY, KEYPAD_K1_MACRO_DELAY_MS, KEYPAD_K1_MACRO_TEXT, KEYPAD_K1_MACRO_ENTER);
#else
      keychord_set(KEYPAD_K1_MODS, KEYPAD_K1_KEY, true);
#endif
    } else {
#if KEYPAD_K1_MODE == 0
      keychord_set(KEYPAD_K1_MODS, KEYPAD_K1_KEY, false);
#endif
    }
  }

  bool k2 = !digitalRead(K2_PIN);
  if (k2Prev != k2) {
    k2Prev = k2;
    key2State = k2;
    key_leds_flush(key1State, key2State);
    if (k2) {
#if KEYPAD_K2_MODE == 1
      macro_run(KEYPAD_K2_MODS, KEYPAD_K2_KEY, KEYPAD_K2_MACRO_DELAY_MS, KEYPAD_K2_MACRO_TEXT, KEYPAD_K2_MACRO_ENTER);
#else
      keychord_set(KEYPAD_K2_MODS, KEYPAD_K2_KEY, true);
#endif
    } else {
#if KEYPAD_K2_MODE == 0
      keychord_set(KEYPAD_K2_MODS, KEYPAD_K2_KEY, false);
#endif
    }
  }

  delay(KEYPAD_DEBOUNCE_MS);
#endif
}
