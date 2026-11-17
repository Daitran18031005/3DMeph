using System.IO;
using Unity.XR.CoreUtils;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.SceneManagement;
using UnityEditor.XR.Management;
using UnityEditor.XR.Management.Metadata;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.XR;
using UnityEngine.Rendering;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.Management;

/// Dựng scene, cấu hình Android/ARCore và build APK không cần thao tác tay:
///   Unity.exe -batchmode -quit -projectPath app/unity_app -executeMethod BuildApp.Build -logFile build.log
public static class BuildApp
{
    const string ScenePath = "Assets/Scenes/Main.unity";
    const string ApkPath = "Build/Room3D.apk";

    public static void Build()
    {
        EditorUserBuildSettings.SwitchActiveBuildTarget(BuildTargetGroup.Android, BuildTarget.Android);
        ConfigurePlayer();
        ConfigureXr();
        CreateScene();
        Directory.CreateDirectory("Build");
        var report = BuildPipeline.BuildPlayer(new[] { ScenePath }, ApkPath, BuildTarget.Android, BuildOptions.None);
        Debug.Log($"[BuildApp] {report.summary.result}, {report.summary.totalSize / 1e6:0.0} MB, {report.summary.totalErrors} lỗi → {ApkPath}");
        EditorApplication.Exit(report.summary.result == UnityEditor.Build.Reporting.BuildResult.Succeeded ? 0 : 1);
    }

    static void ConfigurePlayer()
    {
        var android = NamedBuildTarget.Android;
        PlayerSettings.companyName = "3DMeph";
        PlayerSettings.productName = "Room3D";
        PlayerSettings.SetApplicationIdentifier(android, "com.example.room3d");
        PlayerSettings.SetScriptingBackend(android, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
        PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel26;   // Unity 6.5 bỏ hỗ trợ < 26
        PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.Android, false);
        PlayerSettings.SetGraphicsAPIs(BuildTarget.Android, new[] { GraphicsDeviceType.OpenGLES3 });
        PlayerSettings.defaultInterfaceOrientation = UIOrientation.LandscapeLeft;   // ảnh CPU ARCore nằm ngang: trục camera khớp ảnh
        PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed;       // backend trong LAN chạy http
    }

    static void ConfigureXr()
    {
        if (!EditorBuildSettings.TryGetConfigObject(XRGeneralSettings.k_SettingsKey, out XRGeneralSettingsPerBuildTarget perTarget) || perTarget == null)
        {
            Directory.CreateDirectory("Assets/XR");
            perTarget = ScriptableObject.CreateInstance<XRGeneralSettingsPerBuildTarget>();
            AssetDatabase.CreateAsset(perTarget, "Assets/XR/XRGeneralSettingsPerBuildTarget.asset");
            EditorBuildSettings.AddConfigObject(XRGeneralSettings.k_SettingsKey, perTarget, true);
        }
        if (!perTarget.HasSettingsForBuildTarget(BuildTargetGroup.Android)) perTarget.CreateDefaultSettingsForBuildTarget(BuildTargetGroup.Android);
        if (!perTarget.HasManagerSettingsForBuildTarget(BuildTargetGroup.Android)) perTarget.CreateDefaultManagerSettingsForBuildTarget(BuildTargetGroup.Android);
        var settings = perTarget.SettingsForBuildTarget(BuildTargetGroup.Android);
        settings.InitManagerOnStart = true;
        XRPackageMetadataStore.AssignLoader(settings.Manager, "UnityEngine.XR.ARCore.ARCoreLoader", BuildTargetGroup.Android);
        AssetDatabase.SaveAssets();
    }

    static void CreateScene()
    {
        Directory.CreateDirectory("Assets/Scenes");
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

        var session = new GameObject("AR Session", typeof(ARSession), typeof(ARInputManager)).GetComponent<ARSession>();

        var originGo = new GameObject("XR Origin", typeof(XROrigin), typeof(ARRaycastManager), typeof(ARPlaneManager), typeof(ARPointCloudManager));
        var offset = new GameObject("Camera Offset");
        offset.transform.SetParent(originGo.transform, false);
        var camGo = new GameObject("AR Camera", typeof(Camera), typeof(ARCameraManager), typeof(ARCameraBackground), typeof(TrackedPoseDriver));
        camGo.tag = "MainCamera";
        camGo.transform.SetParent(offset.transform, false);
        var arCam = camGo.GetComponent<Camera>();
        arCam.clearFlags = CameraClearFlags.SolidColor;
        arCam.backgroundColor = Color.black;
        arCam.nearClipPlane = 0.1f;
        var tpd = camGo.GetComponent<TrackedPoseDriver>();
        tpd.positionInput = new InputActionProperty(new InputAction("Position", InputActionType.Value, "<HandheldARInputDevice>/devicePosition"));
        tpd.rotationInput = new InputActionProperty(new InputAction("Rotation", InputActionType.Value, "<HandheldARInputDevice>/deviceRotation"));
        tpd.ignoreTrackingState = true;
        var origin = originGo.GetComponent<XROrigin>();
        origin.Camera = arCam;
        origin.CameraFloorOffsetObject = offset;

        var viewCam = new GameObject("Viewer Camera", typeof(Camera)).GetComponent<Camera>();
        viewCam.clearFlags = CameraClearFlags.SolidColor;
        viewCam.backgroundColor = new Color(0.18f, 0.18f, 0.2f);
        viewCam.nearClipPlane = 0.02f;
        viewCam.enabled = false;

        var light = new GameObject("Light", typeof(Light)).GetComponent<Light>();
        light.type = LightType.Directional;
        light.transform.rotation = Quaternion.Euler(50, -30, 0);
        RenderSettings.ambientLight = new Color(0.55f, 0.55f, 0.55f);

        Directory.CreateDirectory("Assets/Materials");
        var mat = new Material(Shader.Find("Standard")) { color = new Color(0.85f, 0.82f, 0.75f) };
        AssetDatabase.CreateAsset(mat, "Assets/Materials/Model.mat");

        var app = new GameObject("App", typeof(AppMain), typeof(CaptureRecorder), typeof(ModelViewer));
        var rec = app.GetComponent<CaptureRecorder>();
        rec.cameraManager = camGo.GetComponent<ARCameraManager>();
        rec.cameraTransform = camGo.transform;
        var viewer = app.GetComponent<ModelViewer>();
        viewer.viewCamera = viewCam;
        viewer.modelMaterial = mat;
        var main = app.GetComponent<AppMain>();
        main.arSession = session;
        main.arCamera = arCam;
        main.raycaster = originGo.GetComponent<ARRaycastManager>();
        main.recorder = rec;
        main.viewer = viewer;
        main.viewCamera = viewCam;

        EditorSceneManager.SaveScene(scene, ScenePath);
        EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
    }
}
