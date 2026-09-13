import ctypes
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scanner

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
                bundle = root / 'data' / 'scanner_component'
                self.assertTrue((bundle / 'html5-qrcode.min.js').is_file())
                self.assertIn('qr-reader', (bundle / 'index.html').read_text())
                self.assertIn('aspect-ratio: 1', (bundle / 'style.css').read_text())
                self.assertIn('main.js?v=', (bundle / 'index.html').read_text())
                declare.assert_called_once_with('qr_camera', path=str(bundle))


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
            var mode = 'success', allowPlayback = false, decoded, finishStart, cameraIds = [], timers = new Map(), timerId = 0;
            function setTimeout(fn) {timers.set(++timerId, fn); return timerId;}
            function clearTimeout(id) {timers.delete(id);}
            function runTimers() {for (const fn of Array.from(timers.values())) fn();}
            var elements = {};
            for (const id of ['scanner', 'preview', 'placeholder', 'placeholder-text', 'status', 'retry', 'resume', 'camera-choice', 'camera', 'scan-guide']) {
                elements[id] = { hidden: false, textContent: '', style: {},
                    replaceChildren: () => {}, appendChild: () => {},
                    getBoundingClientRect: () => ({height: 470}),
                    addEventListener: (type, fn) => { elements[id][type] = fn; } };
            }
            var window = { parent: { postMessage: msg => messages.push(msg) }, isSecureContext: true,
                addEventListener: (type, fn) => { listeners[type] = fn; } };
            var navigator = { mediaDevices: {getUserMedia: () => {}} };
            var video = {readyState: 4, videoWidth: 640, videoHeight: 480, paused: true,
                srcObject: {getTracks: () => [{stop: () => { tracksStopped++; }}]},
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
            var document = { body: {style: {}}, getElementById: id => elements[id],
                createElement: () => ({}), querySelector: () => video, querySelectorAll: () => [video] };
            var ResizeObserver = class { constructor(fn) {this.fn = fn;} observe() {this.fn();} };
            var Html5Qrcode = class {
                static async getCameras() {
                    return [{id: 'front', label: 'Built-in camera'}, {id: 'rear', label: 'External camera'}];
                }
                async start(camera, config, success) {
                    starts++; decoded = success; cameraIds.push(camera);
                    const box = config.qrbox(400, 300);
                    if (box.width !== box.height || box.width > 300) throw new Error('QR guide is not square');
                    if (mode === 'denied') throw {name: 'NotAllowedError'};
                    if (mode === 'pending') await new Promise(resolve => {finishStart = resolve;});
                }
                async stop() {stops++;}
            };
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
