# ScreenPilot — Product Requirements Document

## Product Goal

Enable AI-driven precise operation of a professional Windows application running inside a VDI, by training a custom neural network to perceive the application's UI elements from screen pixels alone — no accessibility API, no source code access, no OS-level hooks.

## Target Users

- **Primary**: Engineers/operators who need to automate repetitive workflows in a specific VDI-hosted Windows application that has no API and no scripting interface.
- **Secondary**: QA teams who need to regression-test the same application through its GUI.

## Core Use Cases

| # | Use Case | Priority |
|---|----------|----------|
| UC1 | **Real-time cursor awareness**: System continuously reports which UI element (by name/type) the mouse cursor is currently hovering over. | P0 — V1 |
| UC2 | **LLM-driven task execution**: User describes a task in natural language; LLM reasons over detected UI elements and executes a sequence of clicks/keystrokes to complete it. | P0 — V1 |
| UC3 | **Training data collection**: User operates the software normally; system records screenshots + cursor actions for model training. | P0 — V1 |
| UC4 | **Model training & iteration**: User annotates screenshots (with model-assisted pre-labeling), trains a YOLO model, evaluates, and iterates. | P0 — V1 |
| UC5 | **COBOL/Virtel terminal automation**: Automate mainframe operations through a browser-based 3270 terminal emulator. | P1 — V2 |
| UC6 | **Knowledge-enriched operation**: Parse software HTML manual to enrich LLM context with element semantics and workflow definitions. | P1 — V2 |
| UC7 | **Multi-application support**: Package trained models per application; switch between apps dynamically. | P2 — Future |

## Non-Goals (explicitly out of scope)

- **General-purpose UI automation**: ScreenPilot is not Anthropic Computer Use. It targets one specific application at a time, trading generality for precision.
- **Cross-platform agent**: V1 is macOS-only (the machine that views the VDI). The VDI-hosted application can be any OS.
- **Model training infrastructure**: No cloud training pipeline. Training happens locally or on a single GPU machine. Ultralytics CLI is sufficient.
- **Visual overlay / GUI for the tool itself**: V1 is CLI + terminal output. No desktop app, no Electron wrapper.
- **Recording and replaying macros**: ScreenPilot is not a macro recorder. The LLM reasons about each step, adapting to screen state.

## V1 Scope

### What V1 delivers

A CLI tool that, for **one specific VDI-hosted application**:

1. Captures the VDI client window at ~20 FPS
2. Detects screen changes and runs a custom-trained YOLO model only when needed
3. Maintains a real-time UIMap of all detected elements (bounding boxes, classes, OCR text)
4. Reports in terminal which element the cursor is hovering over
5. Accepts natural language tasks, sends UIMap + screenshot to an LLM, executes returned actions
6. Verifies each action succeeded (screen change detection + optional OCR re-check)
7. Includes a data collection mode for building training datasets
8. Includes a training/evaluation wrapper around Ultralytics

### What V1 does NOT deliver

- Virtel/COBOL terminal support (V2)
- Knowledge module / manual parsing (V2)
- Screen classifier for page identification (V2)
- Multi-application model switching (Future)
- GUI / web dashboard (Future)
- Windows/Linux host support (Future)

## Success Metrics

| Metric | Target | How to measure |
|--------|--------|----------------|
| **Task success rate** | ≥ 80% for trained workflows | Run 20 pre-defined tasks end-to-end in dry_run; count how many complete correctly. This is the primary metric. |
| **Element detection mAP@0.5** | ≥ 90% | Ultralytics val on held-out test set |
| **Element detection mAP@0.5:0.95** | ≥ 65% | Ultralytics val on held-out test set |
| **Cursor-to-element latency** | < 50ms after screen change | Benchmark script measures time from frame capture to UIMap update |
| **Click coordinate accuracy** | ≤ 5px from element center | Compare executed click coords vs ground-truth element centers on 50 test cases |
| **False action rate** | < 5% | Percentage of actions that click the wrong element or have no effect |
| **Training data effort** | < 3 days from zero to working model | Clock the full cycle: collection → annotation → training → iteration |

**Primary success criterion**: Task success rate ≥ 80%. mAP is a proxy — what matters is whether the system can actually complete tasks.

## Functional Requirements

### FR1: Screen Capture
- Capture a user-defined screen region (the VDI client window) at ≥ 20 FPS
- Support auto-detection of VDI window by process name
- Support manual region selection as fallback
- Handle Retina (2x) displays correctly

### FR2: Change Detection
- Detect whether the screen content has changed between frames
- Classify change magnitude: NONE / MINOR / MAJOR
- Skip model inference when screen is unchanged
- Tolerate VDI compression noise (not trigger on compression artifacts alone)

### FR3: UI Element Detection
- Run a custom-trained YOLO model on changed frames
- Detect elements with bounding box + class + confidence
- Support ≥ 12 UI element classes (button, menu_item, input_field, checkbox, radio_button, dropdown, dialog, menu_bar, toolbar, label, tab, scrollbar)
- Map model output coordinates back to screen coordinates

### FR4: Element Tracking (UIMap)
- Maintain a persistent map of all detected elements
- Assign stable IDs to elements across frames (IoU matching)
- Build parent-child hierarchy (dialog contains buttons)
- Filter flickering detections (require ≥ 2 frames stability)
- Clear stale elements after major screen changes

### FR5: OCR
- Extract text from each detected element's bounding box
- Used for: element naming in UIMap, pre-click verification, LLM context
- Must handle VDI compression artifacts gracefully

### FR6: Cursor Monitoring
- Track mouse cursor position at ≥ 30 Hz
- Resolve cursor position to the UIMap element it overlaps
- Handle overlapping elements (return smallest/most specific)
- Output current element info to terminal in real-time

### FR7: Action Execution
- Translate element IDs to screen coordinates and execute mouse/keyboard actions
- Support: click, double_click, right_click, type_text, press_key, hotkey, scroll
- Support composite actions: select_menu_item, fill_field
- Verify action effect via change detection (timeout = configurable)
- dry_run mode: log intended actions without executing

### FR8: LLM Integration
- Serialize UIMap into structured text for LLM consumption
- Optionally include screenshot as base64 image
- Parse LLM response into action sequence
- Support at least one cloud LLM provider (Anthropic Claude)

### FR9: Training Data Collection
- Background mode: auto-capture screenshots while user operates the software
- Log cursor position and click events with timestamps
- Export dataset in YOLO format (images/ + labels/ + dataset.yaml)
- Configurable capture interval

### FR10: Model Training Wrapper
- Wrap Ultralytics training API with VDI-specific augmentations
- Support training on MPS (Apple Silicon)
- Export trained model to CoreML
- Evaluation script with per-class mAP breakdown

## Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Host OS | macOS 13+ (Apple Silicon) |
| Python version | 3.11+ |
| Frame-to-UIMap latency | < 50ms (when model runs) |
| Cursor lookup latency | < 1ms |
| Memory usage | < 2 GB resident (excluding model loading) |
| Model inference | < 30ms per frame on M1/M2/M3 |
| No internet required | For inference and cursor monitoring (LLM calls are the exception) |
| Single-process | No Docker, no server, no database. One Python process. |

## Technical Stack Decisions

### Decided

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python 3.11+ | ML ecosystem (Ultralytics, PyTorch, ONNX), rapid iteration |
| Detection model | YOLOv8 (Ultralytics) | Best ecosystem, training CLI, export pipeline, proven for UI detection |
| Training framework | Ultralytics API | Wraps PyTorch; handles augmentation, training, validation, export in one CLI |
| Annotation tool | Label Studio | Open-source, supports model-assisted pre-labeling, YOLO export |
| Pre-labeling | GroundingDINO | Zero-shot UI element detection from text prompts; 80%+ pre-annotation accuracy |
| Action execution | pyautogui | Simple, works on macOS, sufficient for VDI window input |
| Configuration | YAML files | Human-readable, standard |
| LLM provider (V1) | Anthropic Claude API | Best vision + reasoning for UI tasks; computer_use experience |

### Leaning toward (to be validated in Phase 1)

| Decision | Leaning | Alternative | Validation |
|----------|---------|-------------|------------|
| Screen capture | `mss` | ScreenCaptureKit via pyobjc | Benchmark both in Phase 1. mss is simpler; SCK is faster but harder from Python. Go with mss unless it can't hit 20 FPS for VDI window region. |
| Inference runtime | CoreML export | ONNX Runtime + CoreML EP | Export model to both formats, benchmark inference time. CoreML should be faster on ANE, but ONNX is more portable. |
| OCR engine | PaddleOCR | EasyOCR, Tesseract | Test all three on VDI-compressed screenshots. Pick the one with best accuracy on small UI text. |
| Coordinate input | pyautogui | CGEvent via pyobjc | pyautogui for V1. If click precision is insufficient (Retina issues), upgrade to CGEvent. |
| Window detection | Quartz CGWindowList | AppleScript | Quartz is more reliable. AppleScript as fallback for stubborn apps. |

### Not decided (defer to V2+)

| Decision | Options | When to decide |
|----------|---------|----------------|
| Virtel/COBOL approach | Playwright DOM vs screenshot+OCR | When V2 starts; depends on Virtel's DOM structure |
| Knowledge module storage | SQLite vs flat YAML vs in-memory | When manual parsing is implemented |
| Screen classifier architecture | Fine-tuned ResNet vs CLIP-based vs YOLO classification head | After V1 model is stable; needs labeled screen-state data |
| Local LLM | Qwen2.5-VL-7B via Ollama vs llama.cpp | When offline operation becomes a requirement |
| Multi-app model management | Per-app model files vs unified multi-head model | Future, when second application is onboarded |

## Architecture Summary

(Full details in [DESIGN.md](./DESIGN.md))

```
Capture (20 FPS) → Change Detect (<1ms) → YOLO (on change, ~20ms) → UIMap (cached)
                                                                         │
                                          ┌──────────────────────────────┼──────────┐
                                          │                              │          │
                                    Cursor Monitor (60Hz)          LLM Interface   Data Collector
                                    "cursor is on [button] Save"   → reason        → dataset
                                                                   → act
                                                                   → verify
```

Key architectural properties:
- **Single process, multi-threaded**: capture thread + cursor thread + main loop
- **Event-driven model inference**: model only runs when screen changes (not every frame)
- **Cached UIMap**: detection results persist until next screen change; cursor lookup is pure coordinate math
- **Stateless LLM calls**: each call gets full UIMap + screenshot; no conversation memory needed for action execution

## Milestones

### M1: Capture + Change Detection (Week 1)
**Deliverable**: CLI tool that captures VDI window at 20+ FPS, prints "CHANGED" / "UNCHANGED" per frame.
- Screen capture module with mss
- Window finder (auto-detect VDI client)
- Change detector (perceptual hash + SSIM)
- Benchmark script proving ≥ 20 FPS capture, < 5ms change detection
- **Exit criterion**: benchmark passes on actual VDI window

### M2: Training Data Pipeline (Week 2)
**Deliverable**: Data collector that records screenshots + clicks; annotation workflow documented and tested.
- Data collector (background capture + click logging)
- YOLO dataset exporter (images/ + labels/ + dataset.yaml)
- GroundingDINO pre-annotation script
- VDI augmentation transforms
- **Exit criterion**: 50 annotated screenshots produced in under 2 hours (collection + pre-label + correction)

### M3: Trained Model + Detection (Week 3)
**Deliverable**: Trained YOLO model that detects UI elements on target application screenshots with mAP@0.5 > 90%.
- Training wrapper (Ultralytics + augmentations)
- Model evaluation script (per-class mAP)
- Detection module (inference + coordinate mapping)
- Visualization script (draw boxes on screenshots)
- **Exit criterion**: mAP@0.5 > 90% on validation set; visual inspection shows correct boxes

### M4: UIMap + Cursor Monitor (Week 4)
**Deliverable**: Real-time terminal output showing "cursor is on [button] Save" as you move the mouse over the VDI window.
- UIMap data structures
- Element tracker (IoU matching, stability, hierarchy)
- OCR integration for element text
- Cursor monitor (60 Hz polling, hit testing)
- Coordinate transform (Retina-aware)
- **Exit criterion**: cursor monitor correctly identifies element under cursor ≥ 90% of the time during manual testing

### M5: Action Execution + LLM (Week 5-6)
**Deliverable**: End-to-end: describe a task → LLM reasons → actions execute → task completes.
- Action executor (pyautogui + coordinate translation)
- Action verification (post-action change detection)
- LLM interface (UIMap serialization, response parsing)
- Orchestrator (capture → detect → reason → act loop)
- dry_run mode
- **Exit criterion**: task success rate ≥ 80% on 20 predefined test tasks

### M6: Hardening + Documentation (Week 7)
**Deliverable**: Stable, documented V1 ready for daily use.
- Error recovery (retry logic, stale UIMap handling, VDI lag tolerance)
- Configuration documentation
- Training playbook (step-by-step guide for new applications)
- Performance tuning guide
- **Exit criterion**: system runs stable for 1 hour of continuous operation without crashes

## Risks and Open Questions

| Risk | Impact | Mitigation |
|------|--------|------------|
| VDI compression degrades detection accuracy below target | High | Aggressive augmentation during training; validate on real VDI screenshots early (M2) |
| Retina coordinate translation introduces systematic click offset | High | Build coordinate validation test in M4; compare expected vs actual click positions |
| mss capture can't hit 20 FPS for VDI window on macOS | Medium | Benchmark in M1; fallback to ScreenCaptureKit if needed |
| GroundingDINO pre-annotation quality too low for target app | Medium | Test in M2; fallback to OmniParser V2 or manual annotation |
| Small UI elements (checkboxes, 12px icons) undetectable at 640px input | Medium | Train at 1024px input resolution; if still insufficient, go to 1280px |
| LLM hallucinates actions or misidentifies elements | Medium | Pre-click OCR verification; dry_run testing before live execution |
| pyautogui click doesn't register in VDI client | Low | VDI clients accept OS-level input events; test in M1. Fallback: CGEvent |
| Model overfits to current application theme/data | Low | Augmentation + periodic retraining as application updates |

### Open Questions

1. **What OCR engine performs best on VDI-compressed UI text?** — Test PaddleOCR, EasyOCR, Tesseract on real VDI screenshots in M2.
2. **Should the screen classifier be a separate model or a YOLO classification head?** — Defer to V2. V1 relies on LLM to understand screen context from UIMap content.
3. **How to handle application updates that change UI layout?** — Retrain model with updated screenshots. Assess how much layout change requires full retraining vs fine-tuning.
4. **Is pyautogui's Retina handling sufficient or do we need CGEvent?** — Validate in M4 with click accuracy test.
