using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using Unity.Collections;
using UnityEngine;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;

/// Ghi gói quay cho backend (app/README.md): ảnh CPU của ARCore ~2 Hz + intrinsics + T_cam_world (world→camera, quy ước OpenCV, world tay phải, mét).
/// App khoá màn hình LandscapeLeft để trục camera Unity trùng hướng ảnh CPU (cảm biến nằm ngang).
public class CaptureRecorder : MonoBehaviour
{
    public ARCameraManager cameraManager;
    public Transform cameraTransform;
    public float interval = 0.5f;          // giây giữa hai khung (khớp keyframe.fps = 2)
    public int maxSide = 960;              // hạ ảnh CPU cho nhẹ; server còn hạ tiếp về 640
    public float maxSpeed = 0.6f;          // m/s
    public float maxAngular = 60f;         // độ/s

    public bool Recording { get; private set; }
    public int Count => frames.Count;
    public string Warning { get; private set; } = "";
    public string Dir => Path.Combine(Application.persistentDataPath, "capture");

    readonly List<string> frames = new List<string>();
    float lastShot, startTime;
    Vector3 lastPos;
    Quaternion lastRot;

    static readonly Matrix4x4 FlipY = Matrix4x4.Scale(new Vector3(1, -1, 1));   // camera Unity (y lên) → OpenCV (y xuống)
    static readonly Matrix4x4 FlipZ = Matrix4x4.Scale(new Vector3(1, 1, -1));   // world tay trái Unity ↔ tay phải

    public static Vector3 ToRightHanded(Vector3 p) => new Vector3(p.x, p.y, -p.z);

    public void Begin()
    {
        if (Directory.Exists(Dir)) Directory.Delete(Dir, true);
        Directory.CreateDirectory(Path.Combine(Dir, "frames"));
        frames.Clear();
        startTime = Time.time;
        lastPos = cameraTransform.position;
        lastRot = cameraTransform.rotation;
        Recording = true;
    }

    public void End() => Recording = false;

    void Update()
    {
        if (!Recording) return;
        float dt = Mathf.Max(Time.deltaTime, 1e-3f);
        float v = (cameraTransform.position - lastPos).magnitude / dt;
        float w = Quaternion.Angle(cameraTransform.rotation, lastRot) / dt;
        lastPos = cameraTransform.position;
        lastRot = cameraTransform.rotation;
        if (ARSession.state != ARSessionState.SessionTracking) { Warning = "Mất tracking: quay chậm, hướng vào vùng có hoạ tiết"; return; }
        Warning = (v > maxSpeed || w > maxAngular) ? "Di chuyển chậm lại" : "";
        if (Warning != "" || Time.time - lastShot < interval) return;
        if (!cameraManager.TryGetIntrinsics(out XRCameraIntrinsics intr)) return;
        if (!cameraManager.TryAcquireLatestCpuImage(out XRCpuImage img)) return;
        using (img)
        {
            int ds = 1;
            while (Mathf.Max(img.width, img.height) / ds > maxSide) ds *= 2;
            var conv = new XRCpuImage.ConversionParams(img, TextureFormat.RGB24, XRCpuImage.Transformation.MirrorY)
            { outputDimensions = new Vector2Int(img.width / ds, img.height / ds) };
            var buf = new NativeArray<byte>(img.GetConvertedDataSize(conv), Allocator.Temp);
            img.Convert(conv, buf);
            var tex = new Texture2D(conv.outputDimensions.x, conv.outputDimensions.y, TextureFormat.RGB24, false);
            tex.LoadRawTextureData(buf);
            tex.Apply();
            buf.Dispose();
            string name = $"{frames.Count:000000}.jpg";
            File.WriteAllBytes(Path.Combine(Dir, "frames", name), tex.EncodeToJPG(90));
            Destroy(tex);
            float sx = (float)conv.outputDimensions.x / intr.resolution.x, sy = (float)conv.outputDimensions.y / intr.resolution.y;
            Matrix4x4 t = FlipY * cameraTransform.worldToLocalMatrix * FlipZ;
            frames.Add(FrameJson(name, Time.time - startTime, conv.outputDimensions, intr.focalLength.x * sx, intr.focalLength.y * sy,
                                 intr.principalPoint.x * sx, intr.principalPoint.y * sy, t));
            lastShot = Time.time;
        }
    }

    static string F(float x) => x.ToString("R", CultureInfo.InvariantCulture);

    static string FrameJson(string name, float t, Vector2Int size, float fx, float fy, float cx, float cy, Matrix4x4 m)
    {
        var sb = new StringBuilder();
        sb.Append($"{{\"name\":\"{name}\",\"t\":{F(t)},\"w\":{size.x},\"h\":{size.y},\"fx\":{F(fx)},\"fy\":{F(fy)},\"cx\":{F(cx)},\"cy\":{F(cy)},\"T_cam_world\":[");
        for (int r = 0; r < 4; r++)
            sb.Append($"{(r > 0 ? "," : "")}[{F(m[r, 0])},{F(m[r, 1])},{F(m[r, 2])},{F(m[r, 3])}]");
        return sb.Append("]}").ToString();
    }

    /// Ghi capture.json. anchorJson = null (chế độ ar) hoặc {"L_real":…,"A":[…],"B":[…]} (chế độ tape).
    public void WriteMeta(string scaleMode, string anchorJson)
    {
        var sb = new StringBuilder($"{{\"device\":\"{SystemInfo.deviceModel}\",\"scale_mode\":\"{scaleMode}\",");
        if (anchorJson != null) sb.Append($"\"anchor\":{anchorJson},");
        sb.Append("\"frames\":[").Append(string.Join(",", frames)).Append("]}");
        File.WriteAllText(Path.Combine(Dir, "capture.json"), sb.ToString());
    }

    public static string Vec(Vector3 p) => $"[{F(p.x)},{F(p.y)},{F(p.z)}]";
}
