using System;
using System.Text;
using UnityEngine;
using UnityEngine.Rendering;

/// Đọc model.glb do backend xuất (export/mesh.py qua trimesh): mỗi primitive gồm POSITION (float VEC3) + indices (uint8/16/32), tam giác.
/// glTF tay phải → Unity tay trái: đổi dấu x và đảo thứ tự đỉnh tam giác (khoảng cách giữ nguyên).
/// shortcut: bỏ qua transform của node, vật liệu, normal, UV; đủ cho GLB của backend; dùng glTFast nếu cần GLB bất kỳ.
public static class GlbLoader
{
    [Serializable] class Accessor { public int bufferView; public int byteOffset; public int componentType; public int count; public string type; }
    [Serializable] class BufferView { public int byteOffset; public int byteLength; public int byteStride; }
    [Serializable] class Attributes { public int POSITION = -1; }
    [Serializable] class Primitive { public Attributes attributes; public int indices = -1; public int mode = 4; }
    [Serializable] class MeshDef { public Primitive[] primitives; }
    [Serializable] class Gltf { public Accessor[] accessors; public BufferView[] bufferViews; public MeshDef[] meshes; }

    public static Mesh[] Load(byte[] glb)
    {
        if (glb.Length < 20 || BitConverter.ToUInt32(glb, 0) != 0x46546C67) throw new FormatException("không phải GLB");
        int jsonLen = (int)BitConverter.ToUInt32(glb, 12);
        var g = JsonUtility.FromJson<Gltf>(Encoding.UTF8.GetString(glb, 20, jsonLen));
        int bin = 20 + jsonLen + 8;                                   // sau header chunk BIN
        var meshes = new System.Collections.Generic.List<Mesh>();
        foreach (var m in g.meshes)
            foreach (var p in m.primitives)
            {
                if (p.mode != 4 || p.attributes.POSITION < 0 || p.indices < 0) continue;
                var pa = g.accessors[p.attributes.POSITION];
                var pv = g.bufferViews[pa.bufferView];
                int stride = pv.byteStride > 0 ? pv.byteStride : 12, start = bin + pv.byteOffset + pa.byteOffset;
                var verts = new Vector3[pa.count];
                for (int i = 0; i < pa.count; i++)
                {
                    int o = start + i * stride;
                    verts[i] = new Vector3(-BitConverter.ToSingle(glb, o), BitConverter.ToSingle(glb, o + 4), BitConverter.ToSingle(glb, o + 8));
                }
                var ia = g.accessors[p.indices];
                var iv = g.bufferViews[ia.bufferView];
                int istart = bin + iv.byteOffset + ia.byteOffset;
                var idx = new int[ia.count];
                for (int i = 0; i < ia.count; i++)
                    idx[i] = ia.componentType == 5125 ? (int)BitConverter.ToUInt32(glb, istart + 4 * i)
                           : ia.componentType == 5123 ? BitConverter.ToUInt16(glb, istart + 2 * i) : glb[istart + i];
                for (int i = 0; i + 2 < idx.Length; i += 3) (idx[i + 1], idx[i + 2]) = (idx[i + 2], idx[i + 1]);
                var mesh = new Mesh { indexFormat = verts.Length > 65535 ? IndexFormat.UInt32 : IndexFormat.UInt16 };
                mesh.vertices = verts;
                mesh.triangles = idx;
                mesh.RecalculateNormals();
                mesh.RecalculateBounds();
                meshes.Add(mesh);
            }
        return meshes.ToArray();
    }
}
