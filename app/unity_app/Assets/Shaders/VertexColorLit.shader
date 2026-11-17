// Mô hình phòng: màu đỉnh (tô theo độ cao trong GlbLoader) + chiếu sáng Lambert, hai mặt (mesh Poisson có mặt quay ngược).
Shader "Room3D/VertexColorLit"
{
    SubShader
    {
        Tags { "RenderType" = "Opaque" }
        Cull Off
        CGPROGRAM
        #pragma surface surf Lambert vertex:vert
        struct Input { float4 color : COLOR; };
        void vert(inout appdata_full v) { }
        void surf(Input IN, inout SurfaceOutput o) { o.Albedo = IN.color.rgb; }
        ENDCG
    }
    Fallback "Diffuse"
}
