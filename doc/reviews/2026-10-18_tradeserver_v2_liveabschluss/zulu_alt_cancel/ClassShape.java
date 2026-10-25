package zulu.audit;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import org.objectweb.asm.*;

/** Stable instruction/field fingerprint, ignoring debug data and constant pool order. */
public final class ClassShape {
    public static String of(byte[] bytes) {
        StringBuilder header = new StringBuilder();
        SortedMap<String, String> fields = new TreeMap<>(), methods = new TreeMap<>();
        new ClassReader(bytes).accept(new ClassVisitor(Opcodes.ASM9) {
            @Override public void visit(int version, int access, String name, String signature, String parent, String[] interfaces) {
                header.append(version).append('|').append(access).append('|').append(name).append('|')
                        .append(signature).append('|').append(parent).append('|').append(Arrays.toString(interfaces));
            }
            @Override public FieldVisitor visitField(int access, String name, String desc, String signature, Object value) {
                fields.put(name + desc, access + "|" + signature + "|" + value);
                return null;
            }
            @Override public MethodVisitor visitMethod(int access, String name, String desc, String signature, String[] exceptions) {
                StringBuilder body = new StringBuilder(access + "|" + signature + "|" + Arrays.toString(exceptions) + "\n");
                IdentityHashMap<Label, Integer> labels = new IdentityHashMap<>();
                return new MethodVisitor(Opcodes.ASM9) {
                    int label(Label value) { return labels.computeIfAbsent(value, x -> labels.size()); }
                    void add(Object... parts) { body.append(Arrays.deepToString(parts)).append('\n'); }
                    @Override public void visitInsn(int op) { add("insn", op); }
                    @Override public void visitIntInsn(int op, int operand) { add("int", op, operand); }
                    @Override public void visitVarInsn(int op, int var) { add("var", op, var); }
                    @Override public void visitTypeInsn(int op, String type) { add("type", op, type); }
                    @Override public void visitFieldInsn(int op, String owner, String field, String type) { add("field", op, owner, field, type); }
                    @Override public void visitMethodInsn(int op, String owner, String method, String type, boolean face) { add("method", op, owner, method, type, face); }
                    @Override public void visitInvokeDynamicInsn(String method, String type, Handle bootstrap, Object... args) { add("dynamic", method, type, bootstrap, args); }
                    @Override public void visitJumpInsn(int op, Label value) { add("jump", op, label(value)); }
                    @Override public void visitLabel(Label value) { add("label", label(value)); }
                    @Override public void visitLdcInsn(Object value) { add("ldc", value); }
                    @Override public void visitIincInsn(int var, int increment) { add("inc", var, increment); }
                    @Override public void visitTableSwitchInsn(int min, int max, Label fallback, Label... values) {
                        add("table", min, max, label(fallback), Arrays.stream(values).mapToInt(this::label).toArray());
                    }
                    @Override public void visitLookupSwitchInsn(Label fallback, int[] keys, Label[] values) {
                        add("lookup", label(fallback), keys, Arrays.stream(values).mapToInt(this::label).toArray());
                    }
                    @Override public void visitMultiANewArrayInsn(String type, int dimensions) { add("array", type, dimensions); }
                    @Override public void visitTryCatchBlock(Label start, Label end, Label handler, String type) {
                        add("catch", label(start), label(end), handler == null ? -1 : label(handler), type);
                    }
                    @Override public void visitEnd() { methods.put(name + desc, body.toString()); }
                };
            }
        }, ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
        String normalized = header + "\n" + fields + "\n" + methods;
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(normalized.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
    public static void main(String[] args) throws Exception {
        for (String arg : args) System.out.println(of(Files.readAllBytes(Path.of(arg))));
    }
}
