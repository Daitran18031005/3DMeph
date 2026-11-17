using UnityEngine;

/// Xem model.glb (mét, +Y lên) và đo hai điểm theo (30): chạm 2 lần (không kéo) → raycast vào MeshCollider → ‖B − A‖.
/// Một ngón kéo: xoay quanh tâm mô hình; hai ngón: chụm để zoom.
public class ModelViewer : MonoBehaviour
{
    public Camera viewCamera;
    public Material modelMaterial;
    public Material markerMaterial;                         // Unlit/Color: điểm và đoạn đo nổi trên mô hình
    public bool MeasureMode;
    public string Result { get; private set; } = "";

    GameObject root;
    Vector3 center;
    float dist = 4f, yaw = 30f, pitch = 35f;
    Vector2 downPos;
    float downTime;
    readonly Vector3?[] pts = new Vector3?[2];
    GameObject[] markers = new GameObject[2];
    LineRenderer line;

    public bool Load(byte[] glb)
    {
        Clear();
        Mesh[] meshes;
        try { meshes = GlbLoader.Load(glb); } catch (System.Exception e) { Debug.LogError(e); return false; }
        if (meshes.Length == 0) return false;
        root = new GameObject("Model");
        var bounds = meshes[0].bounds;
        foreach (var mesh in meshes)
        {
            var go = new GameObject("Part", typeof(MeshFilter), typeof(MeshRenderer), typeof(MeshCollider));
            go.transform.SetParent(root.transform, false);
            go.GetComponent<MeshFilter>().sharedMesh = mesh;
            go.GetComponent<MeshRenderer>().sharedMaterial = modelMaterial;
            go.GetComponent<MeshCollider>().sharedMesh = mesh;
            bounds.Encapsulate(mesh.bounds);
        }
        center = bounds.center;
        dist = Mathf.Max(bounds.extents.magnitude * 1.6f, 1f);
        UpdateCamera();
        return true;
    }

    public void Clear()
    {
        if (root) Destroy(root);
        ClearMeasure();
    }

    public void ClearMeasure()
    {
        pts[0] = pts[1] = null;
        foreach (var m in markers) if (m) Destroy(m);
        if (line) Destroy(line.gameObject);
        Result = "";
    }

    void Update()
    {
        if (!root || !viewCamera.isActiveAndEnabled) return;
        if (Input.touchCount == 1)
        {
            var t = Input.GetTouch(0);
            if (t.phase == TouchPhase.Began) { downPos = t.position; downTime = Time.time; }
            else if (t.phase == TouchPhase.Moved) { yaw += t.deltaPosition.x * 0.2f; pitch = Mathf.Clamp(pitch - t.deltaPosition.y * 0.2f, -85, 85); }
            else if (t.phase == TouchPhase.Ended && MeasureMode && (t.position - downPos).magnitude < 20 && Time.time - downTime < 0.4f) Pick(t.position);
        }
        else if (Input.touchCount == 2)
        {
            Touch a = Input.GetTouch(0), b = Input.GetTouch(1);
            float prev = ((a.position - a.deltaPosition) - (b.position - b.deltaPosition)).magnitude, now = (a.position - b.position).magnitude;
            if (prev > 1) dist = Mathf.Clamp(dist * prev / now, 0.2f, 50f);
        }
        UpdateCamera();
    }

    void UpdateCamera()
    {
        var rot = Quaternion.Euler(pitch, yaw, 0);
        viewCamera.transform.SetPositionAndRotation(center + rot * new Vector3(0, 0, -dist), rot);
    }

    public void Pick(Vector2 screen)
    {
        if (!Physics.Raycast(viewCamera.ScreenPointToRay(screen), out var hit, 100f)) return;
        int i = pts[0] == null ? 0 : (pts[1] == null ? 1 : -1);
        if (i < 0) { ClearMeasure(); i = 0; }
        pts[i] = hit.point;
        markers[i] = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        Destroy(markers[i].GetComponent<Collider>());
        markers[i].transform.position = hit.point;
        markers[i].transform.localScale = Vector3.one * 0.06f;
        markers[i].GetComponent<Renderer>().sharedMaterial = markerMaterial;
        if (i == 1)
        {
            line = new GameObject("Line").AddComponent<LineRenderer>();
            line.positionCount = 2;
            line.SetPositions(new[] { pts[0].Value, pts[1].Value });
            line.widthMultiplier = 0.02f;
            line.material = markerMaterial;
            Result = $"Khoảng cách: {Vector3.Distance(pts[0].Value, pts[1].Value) * 100f:0.0} cm";
        }
        else Result = "Chạm điểm thứ hai";
    }
}
