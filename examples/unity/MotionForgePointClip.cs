// Minimal Unity point-animation reader for *_unity.json exports.
// Attach to an object and assign the JSON TextAsset and an optional joint root.
using System;
using System.Collections.Generic;
using UnityEngine;

public class MotionForgePointClip : MonoBehaviour
{
    [Serializable] public class JointSample { public string name; public float[] position; }
    [Serializable] public class Frame { public int frame; public float time; public JointSample[] joints; }
    [Serializable] public class Clip { public int schema_version; public float fps; public Frame[] frames; }

    public TextAsset clipJson;
    public Transform jointRoot;
    public float playbackSpeed = 1f;
    public bool loop = true;
    public float sphereScale = 0.045f;

    private Clip clip;
    private readonly Dictionary<string, Transform> markers = new Dictionary<string, Transform>();
    private float elapsed;

    void Start()
    {
        if (clipJson == null) { Debug.LogError("Assign a MotionForge Unity JSON TextAsset."); enabled = false; return; }
        clip = JsonUtility.FromJson<Clip>(clipJson.text);
        if (clip == null || clip.frames == null || clip.frames.Length == 0)
        { Debug.LogError("MotionForge clip has no frames."); enabled = false; return; }
        foreach (var sample in clip.frames[0].joints)
        {
            var marker = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            marker.name = sample.name;
            marker.transform.SetParent(jointRoot != null ? jointRoot : transform, false);
            marker.transform.localScale = Vector3.one * sphereScale;
            markers[sample.name] = marker.transform;
        }
    }

    void Update()
    {
        if (clip == null || clip.frames.Length == 0) return;
        elapsed += Time.deltaTime * playbackSpeed;
        float duration = clip.frames[clip.frames.Length - 1].time;
        if (duration > 0f) elapsed = loop ? Mathf.Repeat(elapsed, duration) : Mathf.Min(elapsed, duration);
        int index = 0;
        while (index + 1 < clip.frames.Length && clip.frames[index + 1].time < elapsed) index++;
        var a = clip.frames[index];
        var b = clip.frames[Mathf.Min(index + 1, clip.frames.Length - 1)];
        float span = b.time - a.time;
        float t = span > 0f ? Mathf.Clamp01((elapsed - a.time) / span) : 0f;
        var lookup = new Dictionary<string, float[]>(b.joints.Length);
        foreach (var item in b.joints) lookup[item.name] = item.position;
        foreach (var item in a.joints)
        {
            if (!markers.TryGetValue(item.name, out var marker) || !lookup.TryGetValue(item.name, out var target)) continue;
            marker.localPosition = Vector3.Lerp(ToVector(item.position), ToVector(target), t);
        }
    }

    static Vector3 ToVector(float[] p) => new Vector3(p[0], p[1], p[2]);
}
