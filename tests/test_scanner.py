import ctypes
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scanner
from qr_utils import generate_qr_code
from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]


class ScannerBundleTests(unittest.TestCase):
    def test_component_serves_local_assets_and_keeps_its_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(ROOT / 'scanner_frontend', root / 'scanner_frontend')
            with patch.object(scanner, 'APP_DIR', root), patch.object(scanner.components, 'declare_component') as declare:
                declare.return_value.return_value = 'REC-0008'
                self.assertEqual(scanner.qrcode_scanner(key='camera_test'), 'REC-0008')
                self.assertTrue(declare.return_value.call_args.kwargs['key'].startswith('camera_test_'))
                self.assertIsNone(declare.return_value.call_args.kwargs['default'])
                bundle = root / 'data' / 'scanner_component_jsqr'
                self.assertTrue((bundle / 'vendor' / 'jsQR.js').is_file())
                self.assertTrue((bundle / 'vendor' / 'LICENSE.jsQR.txt').is_file())
                self.assertTrue((bundle / 'vendor' / 'NOTICES.txt').is_file())
                self.assertFalse((bundle / 'html5-qrcode.min.js').exists())
                self.assertIn('camera-video', (bundle / 'index.html').read_text())
                self.assertIn('aspect-ratio: 1', (bundle / 'style.css').read_text())
                self.assertIn('main.js?v=', (bundle / 'index.html').read_text())
                self.assertIn('vendor/jsQR.js?v=', (bundle / 'index.html').read_text())
                declare.assert_called_once_with('qr_camera_jsqr', path=str(bundle))

    def test_vendored_decoder_is_the_reviewed_unmodified_release(self):
        digest = hashlib.sha256((ROOT / 'scanner_frontend/vendor/jsQR.js').read_bytes()).hexdigest()
        self.assertEqual(digest, 'bc40c8a15196236b2314db0856f72ca0b49980cd5413b8c852a7349f5fee0859')


@unittest.skipUnless(sys.platform == 'darwin', 'JavaScriptCore is available on macOS')
class ScannerCameraTests(unittest.TestCase):
    """Exercise browser lifecycle logic with a fake camera; no hardware access."""
    def setUp(self):
        pointer = ctypes.c_void_p
        self.js = ctypes.CDLL('/System/Library/Frameworks/JavaScriptCore.framework/JavaScriptCore')
        signatures = {
            'JSGlobalContextCreate': ([pointer], pointer),
            'JSGlobalContextRelease': ([pointer], None),
            'JSStringCreateWithUTF8CString': ([ctypes.c_char_p], pointer),
            'JSStringRelease': ([pointer], None),
            'JSEvaluateScript': ([pointer, pointer, pointer, pointer, ctypes.c_int, ctypes.POINTER(pointer)], pointer),
            'JSValueToStringCopy': ([pointer, pointer, ctypes.POINTER(pointer)], pointer),
            'JSStringGetMaximumUTF8CStringSize': ([pointer], ctypes.c_size_t),
            'JSStringGetUTF8CString': ([pointer, pointer, ctypes.c_size_t], ctypes.c_size_t),
        }
        for name, (args, result) in signatures.items():
            getattr(self.js, name).argtypes = args
            getattr(self.js, name).restype = result
        self.context = self.js.JSGlobalContextCreate(None)
        self.addCleanup(self.js.JSGlobalContextRelease, self.context)
        self.evaluate('''
            var messages = [], listeners = {}, starts = 0, stops = 0, tracksStopped = 0;
            var mode = 'success', allowPlayback = false, finishStart, cameraIds = [], timers = new Map(), timerId = 0;
            var nextResult = null, decodeCalls = 0, lastDraw, activeTrack;
            function setTimeout(fn) {timers.set(++timerId, fn); return timerId;}
            function clearTimeout(id) {timers.delete(id);}
            function runTimers() {for (const [id, fn] of Array.from(timers.entries())) {timers.delete(id); fn();}}
            function decoded(text) {nextResult = {data: text}; runTimers();}
            function jsQR() {decodeCalls++; const result = nextResult; nextResult = null; return result;}
            var elements = {};
            for (const id of ['scanner', 'preview', 'placeholder', 'placeholder-text', 'status', 'retry', 'resume', 'camera-choice', 'camera', 'scan-guide']) {
                elements[id] = { hidden: false, textContent: '', style: {},
                    replaceChildren: () => {}, appendChild: () => {},
                    getBoundingClientRect: () => ({height: 470}),
                    addEventListener: (type, fn) => { elements[id][type] = fn; } };
            }
            var window = { parent: { postMessage: msg => messages.push(msg) }, isSecureContext: true,
                addEventListener: (type, fn) => { listeners[type] = fn; } };
            var navigator = { userAgent: '', mediaDevices: {
                getUserMedia: async constraints => {
                    starts++;
                    assert(constraints.audio === false, 'Microphone requested');
                    const id = constraints.video.deviceId?.exact || 'front';
                    cameraIds.push(id);
                    if (mode === 'denied') throw {name: 'NotAllowedError'};
                    if (mode === 'pending') await new Promise(resolve => {finishStart = resolve;});
                    let stopped = false;
                    const track = {getSettings: () => ({deviceId: id}),
                        addEventListener: (name, fn) => {track[name] = fn;},
                        stop: () => {if (!stopped) {stopped = true; stops++; tracksStopped++;}}};
                    activeTrack = track;
                    return {getTracks: () => [track], getVideoTracks: () => [track]};
                },
                enumerateDevices: async () => {
                    if (mode === 'no-enumeration') throw new Error('Unavailable');
                    return [{kind: 'videoinput', deviceId: 'front', label: 'Built-in camera'},
                        {kind: 'videoinput', deviceId: 'rear', label: 'External camera'}];
                }
            } };
            var video = {readyState: 4, videoWidth: 640, videoHeight: 480, paused: true,
                srcObject: null, pause: () => {video.paused = true;},
                setAttribute: () => {}, addEventListener: () => {}, removeEventListener: () => {},
                play: async () => {
                    if (mode === 'autoplay-blocked' && !allowPlayback) {
                        video.paused = true;
                        throw {name: 'NotAllowedError'};
                    }
                    if (mode === 'paused') {video.paused = true; return;}
                    video.paused = false;
                    if (mode === 'no-frames') {video.readyState = 0; video.videoWidth = 0;}
                }
            };
            elements['camera-video'] = video;
            var canvas = {width: 0, height: 0, getContext: () => ({
                drawImage: (...args) => {lastDraw = args;},
                getImageData: () => ({data: new Uint8ClampedArray(4)})
            })};
            var document = { body: {style: {}}, getElementById: id => elements[id],
                createElement: tag => tag === 'canvas' ? canvas : {}, querySelector: () => video, querySelectorAll: () => [video] };
            var ResizeObserver = class { constructor(fn) {this.fn = fn;} observe() {this.fn();} };
            function render() {listeners.message({source: window.parent, data: {type: 'streamlit:render'}});}
            function assert(condition, message) {if (!condition) throw new Error(message);}
        ''')
        self.evaluate((ROOT / 'scanner_frontend' / 'main.js').read_text())

    def evaluate(self, source):
        script = self.js.JSStringCreateWithUTF8CString(source.encode())
        error = ctypes.c_void_p()
        try:
            self.js.JSEvaluateScript(self.context, script, None, None, 1, ctypes.byref(error))
            if error.value:
                message = self.js.JSValueToStringCopy(self.context, error, None)
                try:
                    size = self.js.JSStringGetMaximumUTF8CStringSize(message)
                    buffer = ctypes.create_string_buffer(size)
                    self.js.JSStringGetUTF8CString(message, buffer, size)
                    self.fail(buffer.value.decode())
                finally:
                    self.js.JSStringRelease(message)
        finally:
            self.js.JSStringRelease(script)

    def test_preview_scan_retry_and_camera_release(self):
        self.evaluate("assert(starts === 0, 'Camera started before rendering'); render();")
        self.evaluate("assert(starts === 1 && elements.placeholder.hidden, 'Preview missing'); render();")
        self.evaluate("assert(starts === 1, 'Rerender started duplicate camera'); decoded('REC-0008');")
        self.evaluate("""
            assert(stops === 1 && tracksStopped > 0, 'Camera did not stop after scan');
            assert(messages.some(m => m.type === 'streamlit:setComponentValue' && m.value === 'REC-0008'), 'Missing result');
            assert(!elements.retry.hidden, 'Scan again unavailable');
            assert(messages.filter(m => m.type === 'streamlit:setFrameHeight').every(m => m.height > 0), 'Invisible iframe');
            elements.retry.click();
        """)
        self.evaluate("assert(starts === 2, 'Retry did not start camera'); listeners.pagehide();")
        self.evaluate("assert(stops === 2, 'Camera remained active after leaving');")

    def test_permission_failure_is_visible_and_retryable(self):
        self.evaluate("mode = 'denied'; render();")
        self.evaluate("""
            assert(elements.status.textContent.includes('denied'), 'Permission error not visible');
            assert(!elements.retry.hidden, 'Retry missing');
            mode = 'success'; elements.retry.click();
        """)
        self.evaluate("assert(starts === 2 && elements.placeholder.hidden, 'Retry failed');")

    def test_leaving_while_camera_permission_is_pending(self):
        self.evaluate("mode = 'pending'; render();")
        self.evaluate("listeners.pagehide(); finishStart();")
        self.evaluate("assert(stops === 1 && tracksStopped > 0, 'Late camera stream was not stopped');")

    def test_no_frames_keeps_placeholder_then_shows_recovery_message(self):
        self.evaluate("mode = 'no-frames'; render();")
        self.evaluate("""
            assert(!elements.placeholder.hidden, 'Placeholder hidden before video frames arrived');
            assert(elements.status.textContent.includes('Waiting'), 'Premature success message');
            runTimers();
        """)
        self.evaluate("""
            assert(elements.status.textContent.includes('no video arrived'), 'Missing stalled-preview message');
            assert(!elements.retry.hidden && !elements.camera.disabled, 'Recovery controls unavailable');
            assert(tracksStopped > 0, 'Stalled stream was not released');
        """)

    def test_switch_camera_stops_previous_stream(self):
        self.evaluate("render();")
        self.evaluate("""
            assert(cameraIds[0] === 'front', 'Unexpected initial camera');
            assert(!elements['camera-choice'].hidden, 'Camera selector hidden');
            elements.camera.value = 'rear'; elements.camera.change();
        """)
        self.evaluate("assert(stops === 1 && cameraIds[1] === 'rear', 'Camera switch failed');")

    def test_autoplay_blocked_can_resume_existing_stream_and_scan(self):
        self.evaluate("mode = 'autoplay-blocked'; render();")
        self.evaluate("""
            assert(!elements.placeholder.hidden && !elements.resume.hidden, 'Playback recovery missing');
            assert(elements.status.textContent.includes('Autoplay'), 'No autoplay guidance');
            assert(!elements.status.textContent.includes('access was denied'), 'Misreported camera permission');
            assert(stops === 0 && tracksStopped === 0, 'Blocked stream must stay attached for direct play');
            elements.resume.click();
        """)
        self.evaluate("""
            assert(!elements.resume.hidden && !elements.resume.disabled, 'Repeated block prevents retry');
            allowPlayback = true; elements.resume.click();
        """)
        self.evaluate("""
            assert(elements.placeholder.hidden && elements.resume.hidden, 'Preview did not recover');
            assert(starts === 1 && stops === 0, 'Recovery restarted the stream');
            decoded('REC-0008');
        """)
        self.evaluate("""
            assert(stops === 1 && tracksStopped > 0, 'Recovered camera not released');
            assert(messages.some(m => m.type === 'streamlit:setComponentValue' && m.value === 'REC-0008'), 'Recovered scan missing');
        """)

    def test_paused_video_with_ready_frames_is_not_reported_as_live(self):
        self.evaluate("mode = 'paused'; render();")
        self.evaluate("""
            assert(!elements.placeholder.hidden, 'Paused video falsely reported as live');
            runTimers();
        """)
        self.evaluate("""
            assert(!elements.resume.hidden, 'Paused preview has no recovery');
            listeners.pagehide();
        """)
        self.evaluate("assert(stops === 1 && tracksStopped > 0, 'Paused camera leaked after leaving');")

    def test_camera_switch_is_available_when_autoplay_is_blocked(self):
        self.evaluate("mode = 'autoplay-blocked'; render();")
        self.evaluate("""
            assert(!elements.camera.disabled, 'Camera choice blocked');
            mode = 'success'; elements.camera.value = 'rear'; elements.camera.change();
        """)
        self.evaluate("""
            assert(stops === 1 && starts === 2 && cameraIds[1] === 'rear', 'Camera switch failed');
            assert(elements.placeholder.hidden && elements.resume.hidden, 'Switched preview missing');
        """)

    def test_default_camera_works_when_enumeration_is_unavailable(self):
        self.evaluate("mode = 'no-enumeration'; render();")
        self.evaluate("assert(elements.placeholder.hidden && decodeCalls > 0, 'Default camera cannot scan');")

    def test_decoder_missing_does_not_request_camera(self):
        self.evaluate("jsQR = undefined; render();")
        self.evaluate("assert(starts === 0 && !elements.retry.hidden, 'Missing decoder requested camera');")

    def test_decoding_uses_square_guide_and_stops_after_result(self):
        self.evaluate('render();')
        self.evaluate("""
            assert(lastDraw[3] === lastDraw[4] && lastDraw[3] === 480 * .68, 'Wrong source crop');
            assert(lastDraw[1] === (640 - 480 * .68) / 2, 'Off-centre crop');
            decoded('REC-10000');
        """)
        self.evaluate("""
            const previous = decodeCalls;
            decoded('REC-10000');
            assert(decodeCalls === previous, 'Decoder continued after scan');
            assert(messages.filter(m => m.value === 'REC-10000').length === 1, 'Duplicate result');
            assert(video.srcObject === null, 'Video still owns stream');
        """)

    def test_unplugged_camera_releases_stream_and_offers_retry(self):
        self.evaluate('render();')
        self.evaluate('activeTrack.ended();')
        self.evaluate("assert(stops === 1 && !elements.retry.hidden, 'Unplugged camera has no recovery');")

    def test_real_decoder_reads_existing_record_qr_labels(self):
        self.evaluate((ROOT / 'scanner_frontend/vendor/jsQR.js').read_text())
        with tempfile.TemporaryDirectory() as folder:
            for record_id in ['REC-0008', 'REC-10000']:
                filename = generate_qr_code(record_id, Path(folder))
                with Image.open(Path(folder) / filename) as image:
                    base = image.convert('RGB')
                variants = [base, base.rotate(90), ImageOps.invert(base), base.filter(ImageFilter.GaussianBlur(.6))]
                for index, image in enumerate(variants):
                    with self.subTest(record_id=record_id, variant=index):
                        pixels = list(image.convert('RGBA').tobytes())
                        self.evaluate(f"""
                            var result = jsQR(new Uint8ClampedArray({json.dumps(pixels)}), {image.width}, {image.height});
                            assert(result && result.data === {json.dumps(record_id)}, 'Real decoder failed label');
                        """)
        self.evaluate("assert(jsQR(new Uint8ClampedArray(100 * 100 * 4).fill(255), 100, 100) === null, 'Blank image false positive');")
