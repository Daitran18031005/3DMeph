using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;

/// Luồng của app (ĐC §19 Hình 23): Quay → Gửi (POST /jobs) → hỏi tiến độ (GET /jobs/{id}) → tải GLB → Xem & đo.
/// Hai chế độ scale: "ar" (quỹ đạo ARCore) và "tape" (chạm 2 đầu mút trên AR + nhập số thước dây).
public class AppMain : MonoBehaviour
{
    public ARSession arSession;
    public Camera arCamera;
    public ARRaycastManager raycaster;
    public CaptureRecorder recorder;
    public ModelViewer viewer;
    public Camera viewCamera;

    [System.Serializable]
    class JobStatus { public string status; public string stage; public float progress; public string error_code; public string message; }

    [System.Serializable]
    class JobCreated { public string job_id; }

    Text status, warn;
    InputField serverField, lengthField;
    Button recBtn, modeBtn, sendBtn, viewBtn, measureBtn, newBtn, clearAnchorBtn;
    string scaleMode = "ar", jobId;
    readonly Vector3?[] anchor = new Vector3?[2];
    readonly GameObject[] anchorMarks = new GameObject[2];
    Font font;

    void Start()
    {
        Screen.orientation = ScreenOrientation.LandscapeLeft;
        Screen.sleepTimeout = SleepTimeout.NeverSleep;
        font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        BuildUi();
        ShowCapture();
    }

    // ------------------------------------------------------------------ UI
    void BuildUi()
    {
        var canvas = new GameObject("Canvas", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster)).GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        var scaler = canvas.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920, 1080);
        if (!FindAnyObjectByType<UnityEngine.EventSystems.EventSystem>())
            new GameObject("EventSystem", typeof(UnityEngine.EventSystems.EventSystem), typeof(UnityEngine.EventSystems.StandaloneInputModule));
        var t = canvas.transform;
        status = MakeText(t, new Vector2(0, 1), new Vector2(30, -30), new Vector2(1400, 120), 40);
        warn = MakeText(t, new Vector2(0.5f, 0.5f), new Vector2(-500, 60), new Vector2(1000, 90), 52);
        warn.color = new Color(1f, 0.35f, 0.2f);
        warn.alignment = TextAnchor.MiddleCenter;
        serverField = MakeInput(t, new Vector2(1, 1), new Vector2(-640, -30), new Vector2(610, 90), PlayerPrefs.GetString("server", "http://192.168.1.10:8000"));
        lengthField = MakeInput(t, new Vector2(1, 1), new Vector2(-640, -140), new Vector2(610, 90), "");
        lengthField.placeholder.GetComponent<Text>().text = "Thước dây (cm)";
        lengthField.contentType = InputField.ContentType.DecimalNumber;
        float y = 30;
        recBtn = MakeButton(t, new Vector2(30, y), "Ghi", ToggleRecord);
        modeBtn = MakeButton(t, new Vector2(340, y), "Scale: AR", ToggleMode);
        clearAnchorBtn = MakeButton(t, new Vector2(650, y), "Xoá mốc", ClearAnchor);
        sendBtn = MakeButton(t, new Vector2(960, y), "Gửi", () => StartCoroutine(Send()));
        viewBtn = MakeButton(t, new Vector2(1270, y), "Xem mô hình", () => StartCoroutine(DownloadAndView()));
        measureBtn = MakeButton(t, new Vector2(30, y), "Đo: tắt", ToggleMeasure);
        newBtn = MakeButton(t, new Vector2(340, y), "Quay mới", ShowCapture);
    }

    Text MakeText(Transform parent, Vector2 anchorPt, Vector2 pos, Vector2 size, int fontSize)
    {
        var go = new GameObject("Text", typeof(RectTransform), typeof(Text));
        go.transform.SetParent(parent, false);
        var rt = go.GetComponent<RectTransform>();
        rt.anchorMin = rt.anchorMax = rt.pivot = anchorPt;
        rt.anchoredPosition = pos;
        rt.sizeDelta = size;
        var txt = go.GetComponent<Text>();
        txt.font = font;
        txt.fontSize = fontSize;
        txt.color = Color.white;
        var outline = go.AddComponent<Outline>();
        outline.effectColor = Color.black;
        return txt;
    }

    Button MakeButton(Transform parent, Vector2 pos, string label, UnityEngine.Events.UnityAction onClick)
    {
        var go = new GameObject(label, typeof(RectTransform), typeof(Image), typeof(Button));
        go.transform.SetParent(parent, false);
        var rt = go.GetComponent<RectTransform>();
        rt.anchorMin = rt.anchorMax = rt.pivot = Vector2.zero;
        rt.anchoredPosition = pos;
        rt.sizeDelta = new Vector2(290, 110);
        go.GetComponent<Image>().color = new Color(0.1f, 0.45f, 0.85f, 0.9f);
        go.GetComponent<Button>().onClick.AddListener(onClick);
        var txt = MakeText(go.transform, new Vector2(0.5f, 0.5f), Vector2.zero, rt.sizeDelta, 40);
        txt.alignment = TextAnchor.MiddleCenter;
        txt.text = label;
        return go.GetComponent<Button>();
    }

    InputField MakeInput(Transform parent, Vector2 anchorPt, Vector2 pos, Vector2 size, string value)
    {
        var go = new GameObject("Input", typeof(RectTransform), typeof(Image), typeof(InputField));
        go.transform.SetParent(parent, false);
        var rt = go.GetComponent<RectTransform>();
        rt.anchorMin = rt.anchorMax = anchorPt;
        rt.pivot = new Vector2(0, 1);
        rt.anchoredPosition = pos;
        rt.sizeDelta = size;
        go.GetComponent<Image>().color = new Color(1, 1, 1, 0.85f);
        var field = go.GetComponent<InputField>();
        var text = MakeText(go.transform, new Vector2(0.5f, 0.5f), Vector2.zero, size - new Vector2(20, 10), 36);
        text.color = Color.black;
        text.GetComponent<Outline>().enabled = false;
        var ph = MakeText(go.transform, new Vector2(0.5f, 0.5f), Vector2.zero, size - new Vector2(20, 10), 36);
        ph.color = new Color(0, 0, 0, 0.4f);
        ph.GetComponent<Outline>().enabled = false;
        text.rectTransform.pivot = ph.rectTransform.pivot = new Vector2(0.5f, 0.5f);
        field.textComponent = text;
        field.placeholder = ph;
        field.text = value;
        return field;
    }

    void SetLabel(Button b, string s) => b.GetComponentInChildren<Text>().text = s;

    // ------------------------------------------------------------------ chế độ
    void ShowCapture()
    {
        viewer.Clear();
        viewCamera.enabled = false;
        arCamera.enabled = true;
        arSession.enabled = true;
        foreach (var b in new[] { recBtn, modeBtn, sendBtn }) b.gameObject.SetActive(true);
        foreach (var b in new[] { viewBtn, measureBtn, newBtn }) b.gameObject.SetActive(false);
        serverField.gameObject.SetActive(true);
        UpdateModeUi();
        status.text = "Quét phòng: bấm Ghi, đi chậm quanh phòng, quay cả góc tường và sàn.";
    }

    void ShowViewer()
    {
        recorder.End();
        arSession.enabled = false;
        arCamera.enabled = false;
        viewCamera.enabled = true;
        foreach (var b in new[] { recBtn, modeBtn, sendBtn, viewBtn, clearAnchorBtn }) b.gameObject.SetActive(false);
        foreach (var b in new[] { measureBtn, newBtn }) b.gameObject.SetActive(true);
        serverField.gameObject.SetActive(false);
        lengthField.gameObject.SetActive(false);
        ClearAnchor();
    }

    void ToggleMode()
    {
        scaleMode = scaleMode == "ar" ? "tape" : "ar";
        UpdateModeUi();
    }

    void UpdateModeUi()
    {
        bool tape = scaleMode == "tape";
        SetLabel(modeBtn, tape ? "Scale: Thước" : "Scale: AR");
        lengthField.gameObject.SetActive(tape);
        clearAnchorBtn.gameObject.SetActive(tape);
        if (!tape) ClearAnchor();
    }

    void ToggleRecord()
    {
        if (recorder.Recording) { recorder.End(); SetLabel(recBtn, "Ghi"); }
        else { recorder.Begin(); SetLabel(recBtn, "Dừng"); }
    }

    void ToggleMeasure()
    {
        viewer.MeasureMode = !viewer.MeasureMode;
        SetLabel(measureBtn, viewer.MeasureMode ? "Đo: bật" : "Đo: tắt");
        if (!viewer.MeasureMode) viewer.ClearMeasure();
    }

    // ------------------------------------------------------------------ mốc thước dây (chạm A, B trên AR)
    void ClearAnchor()
    {
        anchor[0] = anchor[1] = null;
        foreach (var m in anchorMarks) if (m) Destroy(m);
    }

    void Update()
    {
        if (arCamera.enabled)
        {
            string s = recorder.Recording ? $"Đang ghi: {recorder.Count} khung" : $"Đã có {recorder.Count} khung";
            if (scaleMode == "tape") s += $" | Mốc: {(anchor[0] == null ? "chạm điểm A" : anchor[1] == null ? "chạm điểm B" : $"đã đặt ({Vector3.Distance(anchor[0].Value, anchor[1].Value) * 100f:0} cm theo AR)")}";
            if (jobId == null) status.text = s;
            warn.text = recorder.Recording ? recorder.Warning : "";
            if (scaleMode == "tape" && Input.touchCount == 1 && Input.GetTouch(0).phase == TouchPhase.Ended
                && !UnityEngine.EventSystems.EventSystem.current.IsPointerOverGameObject(Input.GetTouch(0).fingerId))
                PlaceAnchor(Input.GetTouch(0).position);
        }
        else
        {
            warn.text = "";
            if (viewer.Result != "") status.text = viewer.Result;
        }
    }

    void PlaceAnchor(Vector2 screen)
    {
        var hits = new List<ARRaycastHit>();
        if (!raycaster.Raycast(screen, hits, TrackableType.PlaneWithinPolygon | TrackableType.FeaturePoint)) return;
        int i = anchor[0] == null ? 0 : anchor[1] == null ? 1 : -1;
        if (i < 0) { ClearAnchor(); i = 0; }
        anchor[i] = hits[0].pose.position;
        anchorMarks[i] = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        anchorMarks[i].transform.position = anchor[i].Value;
        anchorMarks[i].transform.localScale = Vector3.one * 0.03f;
    }

    // ------------------------------------------------------------------ mạng
    string Server => serverField.text.TrimEnd('/');

    IEnumerator Send()
    {
        if (recorder.Recording) ToggleRecord();
        if (recorder.Count < 40) { status.text = $"Cần ≥ 40 khung, mới có {recorder.Count}: quay thêm"; yield break; }
        string anchorJson = null;
        if (scaleMode == "tape")
        {
            if (anchor[1] == null || !float.TryParse(lengthField.text, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float cm) || cm <= 0)
            { status.text = "Chế độ thước dây: chạm đủ A, B và nhập số cm"; yield break; }
            anchorJson = $"{{\"L_real\":{(cm / 100f).ToString(System.Globalization.CultureInfo.InvariantCulture)},\"A\":{CaptureRecorder.Vec(CaptureRecorder.ToRightHanded(anchor[0].Value))},\"B\":{CaptureRecorder.Vec(CaptureRecorder.ToRightHanded(anchor[1].Value))}}}";
        }
        PlayerPrefs.SetString("server", Server);
        recorder.WriteMeta(scaleMode, anchorJson);
        string zip = Path.Combine(Application.temporaryCachePath, "capture.zip");
        if (File.Exists(zip)) File.Delete(zip);
        ZipFile.CreateFromDirectory(recorder.Dir, zip);
        status.text = "Đang gửi…";
        var form = new WWWForm();
        form.AddBinaryData("capture", File.ReadAllBytes(zip), "capture.zip", "application/zip");
        using (var req = UnityWebRequest.Post(Server + "/jobs", form))
        {
            yield return req.SendWebRequest();
            if (req.result != UnityWebRequest.Result.Success) { status.text = $"Gửi lỗi: {req.error} {req.downloadHandler.text}"; yield break; }
            jobId = JsonUtility.FromJson<JobCreated>(req.downloadHandler.text).job_id;
        }
        while (true)
        {
            using (var req = UnityWebRequest.Get($"{Server}/jobs/{jobId}"))
            {
                yield return req.SendWebRequest();
                if (req.result == UnityWebRequest.Result.Success)
                {
                    var st = JsonUtility.FromJson<JobStatus>(req.downloadHandler.text);
                    status.text = $"Job {jobId}: {st.status} ({st.progress * 100f:0}%)" + (st.status == "failed" ? $" — lỗi {st.error_code}" : "");
                    if (st.status == "done") { viewBtn.gameObject.SetActive(true); yield break; }
                    if (st.status == "failed") { jobId = null; yield break; }
                }
            }
            yield return new WaitForSeconds(3f);
        }
    }

    IEnumerator DownloadAndView()
    {
        status.text = "Đang tải mô hình…";
        using (var req = UnityWebRequest.Get($"{Server}/jobs/{jobId}/result"))
        {
            yield return req.SendWebRequest();
            if (req.result != UnityWebRequest.Result.Success) { status.text = $"Tải lỗi: {req.error}"; yield break; }
            ShowViewer();
            status.text = viewer.Load(req.downloadHandler.data) ? "Bật Đo rồi chạm 2 điểm trên mô hình" : "Không đọc được model.glb";
            jobId = null;
        }
    }
}
