import bpy
import json
import os

# --- CONFIGURATION ---
ARMATURE_NAME = "Armature"

def import_motionforge_data(filepath):
    if not os.path.exists(filepath):
        print(f"Error: File not found {filepath}")
        return None
    
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data

def animate_armature(data):
    obj = bpy.data.objects.get(ARMATURE_NAME)
    if not obj or obj.type != 'ARMATURE':
        # Create a simple armature if it doesn't exist
        print(f"Armature '{ARMATURE_NAME}' not found, creating one...")
        bpy.ops.object.armature_add()
        obj = bpy.context.active_object
        obj.name = ARMATURE_NAME

    # Set to pose mode
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='POSE')
    
    frames = data.get("frames", [])
    print(f"Animating {len(frames)} frames...")

    for frame_data in frames:
        frame_num = frame_data["frame"]
        joints = frame_data["joints"]
        
        for joint_name, pos in joints.items():
            bone = obj.pose.bones.get(joint_name)
            if not bone:
                # Add bone if it doesn't exist (First frame only)
                if frame_num == frames[0]["frame"]:
                    bpy.ops.object.mode_set(mode='EDIT')
                    edit_bone = obj.data.edit_bones.new(joint_name)
                    edit_bone.head = (pos[0], pos[1], pos[2])
                    edit_bone.tail = (pos[0], pos[1], pos[2] + 0.1)
                    bpy.ops.object.mode_set(mode='POSE')
                    bone = obj.pose.bones.get(joint_name)
            
            if bone:
                # Apply position (Note: for real skeletons you'd use rotations, 
                # but for point-cloud validation this is perfect)
                bone.location = (pos[0], pos[2], -pos[1]) # Map to Blender World
                bone.keyframe_insert(data_path="location", frame=frame_num)

    print("Animation done.")

# --- UI OPERATOR ---
class ImportMocapOperator(bpy.types.Operator):
    bl_idname = "import.motionforge_json"
    bl_label = "Import MotionForge JSON"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        data = import_motionforge_data(self.filepath)
        if data:
            animate_armature(data)
            return {'FINISHED'}
        return {'CANCELLED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

def register():
    bpy.utils.register_class(ImportMocapOperator)

def unregister():
    bpy.utils.unregister_class(ImportMocapOperator)

if __name__ == "__main__":
    # If running from Scripting tab, just call the operator
    register()
    bpy.ops.import.motionforge_json('INVOKE_DEFAULT')
