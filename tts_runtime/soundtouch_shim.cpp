#include <soundtouch/SoundTouch.h>
#include <type_traits>
#include <exception>
static_assert(std::is_same<soundtouch::SAMPLETYPE, float>::value, "Float SoundTouch required");
static thread_local const char *last_error = "";
extern "C" {
const char *st_error() { return last_error; }
void *st_create(double tempo) {
    try {
        auto *s = new soundtouch::SoundTouch();
        s->setSampleRate(24000); s->setChannels(1);
        s->setRate(1.0); s->setPitch(1.0); s->setTempo(tempo);
        s->setSetting(SETTING_USE_QUICKSEEK, 0);
        return s;
    } catch (...) { last_error = "SoundTouch initialization failed"; return nullptr; }
}
int st_put(void *p, const float *audio, unsigned frames) {
    try { static_cast<soundtouch::SoundTouch *>(p)->putSamples(audio, frames); return 0; }
    catch (...) { last_error = "SoundTouch putSamples failed"; return -1; }
}
int st_flush(void *p) {
    try { static_cast<soundtouch::SoundTouch *>(p)->flush(); return 0; }
    catch (...) { last_error = "SoundTouch flush failed"; return -1; }
}
unsigned st_receive(void *p, float *audio, unsigned frames) {
    return static_cast<soundtouch::SoundTouch *>(p)->receiveSamples(audio, frames);
}
void st_destroy(void *p) { delete static_cast<soundtouch::SoundTouch *>(p); }
}
