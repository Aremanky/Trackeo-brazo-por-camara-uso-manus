"""
CFFI builder for Manus SDK
This script automatically processes the C headers and generates Python bindings
"""
import os
import sys
import re
from pathlib import Path
from cffi import FFI

ffibuilder = FFI()


def preprocess_header(header_path):
    """
    Preprocess C header file to extract declarations suitable for CFFI.
    Removes preprocessor directives, extern "C" blocks, CORESDK_API markers, etc.
    """
    with open(header_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove C++ extern "C" blocks but keep the content
    content = re.sub(r'extern\s+"C"\s*\{', '', content)
    content = re.sub(r'^\s*\}\s*$', '', content, flags=re.MULTILINE)
    
    # Remove CORESDK_API and other DLL export macros
    content = re.sub(r'\bCORESDK_API\b\s*', '', content)
    content = re.sub(r'\b__declspec\([^)]*\)\s*', '', content)
    content = re.sub(r'\b__attribute__\([^)]*\)\s*', '', content)
    
    # Remove comments EARLY so they don't interfere with #define processing
    # Remove single-line // comments (but keep /// doc comments)
    content = re.sub(r'(?<!/)//(?!/)\s*.*?$', '', content, flags=re.MULTILINE)
    
    # Remove /* */ comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # Remove #include directives
    content = re.sub(r'^\s*#include\s+[<"].*?[>"]\s*$', '', content, flags=re.MULTILINE)
    
    # Remove ALL preprocessor directives except simple #define constants
    # Remove #ifdef, #ifndef, #if, #else, #elif, #endif, #error, #pragma, etc.
    content = re.sub(r'^\s*#\s*ifdef\b.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*#\s*ifndef\b.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*#\s*if\b.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*#\s*elif\b.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*#\s*else\b.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*#\s*endif\b.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*#\s*error\b.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*#\s*pragma\b.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*#\s*undef\b.*$', '', content, flags=re.MULTILINE)
    
    # Remove #define for complex macros but keep simple constants
    # Keep #define CONSTANT_NAME value
    # Remove #define FUNCTION_LIKE(x) ...
    content = re.sub(r'^\s*#define\s+\w+\([^)]*\).*?$', '', content, flags=re.MULTILINE)
    
    # Remove #define with string values (CFFI can't handle these - they cause compiler errors)
    content = re.sub(r'^\s*#define\s+\w+\s+"[^"]*"\s*$', '', content, flags=re.MULTILINE)
    
    # Remove include guard #defines (they typically start/end with _, end with _H, etc.)
    content = re.sub(r'^\s*#define\s+__?\w*_H(PP)?__?\s*$', '', content, flags=re.MULTILINE)
    
    # Process #define constants - evaluate expressions where possible
    # CFFI needs actual numeric values for array sizes, but can use ... for other cases
    defines = {}
    
    def collect_define(match):
        define_name = match.group(1)
        define_value = match.group(2).strip()
        defines[define_name] = define_value
        return match.group(0)
    
    # First pass: collect all defines
    re.sub(r'^\s*#define\s+(\w+)\s+(.+)$', collect_define, content, flags=re.MULTILINE)
    
    # Second pass: try to resolve define values
    def resolve_define(name, depth=0):
        if depth > 10:  # Prevent infinite recursion
            return None
        if name not in defines:
            return None
        value = defines[name]
        # If it's already a simple number, return it
        if re.match(r'^(0x[\da-fA-F]+|\d+)$', value):
            try:
                return str(eval(value))  # Normalize hex to decimal
            except:
                return value
        # Try to resolve references and evaluate
        try:
            # Replace identifiers with their values
            resolved = value
            for other_name in defines.keys():
                if other_name in resolved:
                    other_val = resolve_define(other_name, depth + 1)
                    if other_val is not None:
                        resolved = re.sub(r'\b' + other_name + r'\b', other_val, resolved)
            # Now try to evaluate the expression (only if it looks like valid Python)
            resolved = resolved.replace(' ', '')  # Remove spaces
            # Check if it's a valid expression (no dots except in floats, only math operators)
            if re.match(r'^[\d+\-*/()]+$', resolved):
                result = eval(resolved)
                return str(int(result))  # Convert to int
            return None  # Can't evaluate
        except:
            return None
    
    # Third pass: replace defines with resolved values or ...
    def simplify_define(match):
        define_name = match.group(1)
        define_value = match.group(2).strip()
        # Try to resolve to a number
        resolved = resolve_define(define_name)
        if resolved is not None:
            return f'#define {define_name} {resolved}'
        else:
            # Can't resolve - use ...
            return f'#define {define_name} ...'
    
    content = re.sub(r'^\s*#define\s+(\w+)\s+(.+)$', simplify_define, content, flags=re.MULTILINE)
    
    # Remove deprecated attributes
    content = re.sub(r'\[\[deprecated\([^]]*\)\]\]\s*', '', content)
    
    # Remove default parameter values in function declarations (C++ feature not supported by CFFI)
    # This matches "= value" only within function parameter lists (between parentheses)
    # We need to be more careful to not match struct member comments
    def remove_default_params(match):
        # Get the full function declaration
        func_decl = match.group(0)
        # Remove default values from parameters (= value before , or ))
        func_decl = re.sub(r'=\s*[^,)]+\s*(?=[,)])', '', func_decl)
        return func_decl
    
    # Match function declarations and remove their default parameters
    content = re.sub(r'(\w+\s+\w+\([^)]*\)\s*;)', remove_default_params, content)
    
    # Clean up multiple blank lines
    content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
    
    return content


def extract_relevant_declarations(content):
    """
    Extract only the declarations we need for CFFI.
    This includes typedefs, enums, structs, and function declarations.
    """
    lines = []
    in_declaration = False
    bracket_count = 0
    current_decl = []
    
    for line in content.split('\n'):
        stripped = line.strip()
        
        # Skip empty lines when not in declaration
        if not stripped and not in_declaration:
            continue
        
        # Skip ALL preprocessor directives except simple #define constants
        if stripped.startswith('#'):
            # Only keep simple #define CONSTANT VALUE (no parentheses, no strings)
            if stripped.startswith('#define'):
                parts = stripped.split(maxsplit=2)  # Split into: #define, NAME, VALUE
                if len(parts) >= 3 and '(' not in parts[1]:
                    # Skip string literals (values starting with ")
                    if not parts[2].strip().startswith('"'):
                        lines.append(line)
            continue
        
        # Start of a declaration
        if any(stripped.startswith(kw) for kw in ['typedef', 'struct', 'enum', 'CORESDK_API']) or \
           (stripped and not stripped.startswith('#') and 'CoreSdk_' in stripped):
            in_declaration = True
            current_decl = [line]
            bracket_count = line.count('{') - line.count('}')
            
            # Check if declaration ends on same line
            if ';' in line and bracket_count == 0:
                lines.append(line)
                in_declaration = False
                current_decl = []
            continue
        
        # Continue declaration
        if in_declaration:
            current_decl.append(line)
            bracket_count += line.count('{') - line.count('}')
            
            # Check if declaration is complete
            if ';' in line and bracket_count == 0:
                lines.extend(current_decl)
                in_declaration = False
                current_decl = []
    
    return '\n'.join(lines)


def extract_enums_from_header(header_path):
    """
    Extract enum definitions from C header and return Python IntEnum code.
    Returns dict of {enum_name: {member_name: value}}
    """
    with open(header_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    enums = {}
    # Match: typedef enum EnumName { ... } EnumName;
    enum_pattern = r'typedef\s+enum\s+(\w+)\s*\{([^}]+)\}\s*\1;'
    
    for match in re.finditer(enum_pattern, content, re.DOTALL):
        enum_name = match.group(1)
        enum_body = match.group(2)
        
        # Parse enum values
        values = {}
        counter = 0
        
        for line in enum_body.split(','):
            # Remove C++ and C comments
            line = re.sub(r'//.*$', '', line, flags=re.MULTILINE)
            line = re.sub(r'/\*.*?\*/', '', line, flags=re.DOTALL)
            line = line.strip()
            
            if not line:
                continue
            
            # Handle multi-line comments that might remain
            if '/*' in line or '*/' in line:
                continue
            
            if '=' in line:
                # Explicit value assignment
                parts = line.split('=')
                name = parts[0].strip()
                value_str = parts[1].strip()
                
                # Skip if name is empty or invalid
                if not name or not name.replace('_', '').isalnum():
                    continue
                
                try:
                    # Try to evaluate the value (could be 0x hex, or arithmetic)
                    value = int(value_str, 0) if value_str.startswith('0x') else int(eval(value_str))
                    values[name] = value
                    counter = value + 1
                except:
                    values[name] = counter
                    counter += 1
            else:
                # Auto-increment
                # Skip if name is empty or invalid
                if not line or not line.replace('_', '').isalnum():
                    continue
                values[line] = counter
                counter += 1
        
        if values:
            enums[enum_name] = values
    
    return enums


def generate_python_enums(enums):
    """Generate Python code with IntEnum classes from extracted enums."""
    import keyword
    
    code = '"""\nAuto-generated Python enums from Manus SDK headers\nDo not edit manually - regenerate with build_ffi.py\n"""\n'
    code += 'from enum import IntEnum\n\n'
    
    for enum_name, values in sorted(enums.items()):
        code += f'class {enum_name}(IntEnum):\n'
        code += f'    """Auto-generated from {enum_name}"""\n'
        
        for name, value in sorted(values.items(), key=lambda x: x[1]):
            # Strip the enum name prefix if it exists (e.g., SDKReturnCode_Success -> Success)
            clean_name = name
            prefix = f'{enum_name}_'
            if name.startswith(prefix):
                clean_name = name[len(prefix):]
            
            # Fix invalid Python identifiers
            if clean_name[0].isdigit():
                clean_name = f'_{clean_name}'
            
            # Fix Python keywords (None, True, False, etc.)
            if keyword.iskeyword(clean_name) or clean_name in ('None', 'True', 'False'):
                clean_name = f'{clean_name}_'
            
            # Keep both the original and clean name for compatibility
            code += f'    {clean_name} = {value}\n'
            # Only add alias if it's different and valid
            if clean_name != name and not name[0].isdigit() and not keyword.iskeyword(name):
                code += f'    {name} = {value}  # Full name alias\n'
        
        code += '\n\n'
    
    # Add __all__ for easy import
    code += '__all__ = [\n'
    for enum_name in sorted(enums.keys()):
        code += f'    "{enum_name}",\n'
    code += ']\n'
    
    return code


def build_cdef_from_headers(sdk_include_path):
    """
    Build CFFI cdef string from Manus SDK headers.
    """
    # Read and preprocess headers
    # Process ManusSDKTypes.h first (has all type definitions)
    # Then ManusSDK.h (has function declarations, may have forward type references)
    types_header = os.path.join(sdk_include_path, 'ManusSDKTypes.h')
    sdk_header = os.path.join(sdk_include_path, 'ManusSDK.h')
    
    print(f"Processing {types_header}...")
    types_content = preprocess_header(types_header)
    types_decls = extract_relevant_declarations(types_content)
    
    print(f"Processing {sdk_header}...")
    sdk_content = preprocess_header(sdk_header)
    sdk_decls = extract_relevant_declarations(sdk_content)
    
    # Extract and generate Python enums
    print(f"Extracting enums from {types_header}...")
    enums = extract_enums_from_header(types_header)
    print(f"Found {len(enums)} enums")
    
    # Generate Python enum code
    enum_code = generate_python_enums(enums)
    enum_file = os.path.join(os.path.dirname(__file__), 'generated', '_enums.py')
    with open(enum_file, 'w', encoding='utf-8') as f:
        f.write(enum_code)
    print(f"Generated Python enums in: {enum_file}")
    
    # Combine: types first (full definitions), then SDK functions
    # This ensures all types are fully defined before being referenced
    cdef = types_decls + '\n\n' + sdk_decls
    
    # Add Python callback declarations for extern "Python" functions
    # These allow Python functions to be called from C callbacks
    cdef += '\n\n// Python callbacks - extern "Python" declarations\n'
    cdef += 'extern "Python" void python_raw_skeleton_callback(const SkeletonStreamInfo* const p_SkeletonInfo);\n'
    cdef += 'extern "Python" void python_skeleton_callback(const SkeletonStreamInfo* const p_SkeletonInfo);\n'
    cdef += 'extern "Python" void python_landscape_callback(const Landscape* const p_Landscape);\n'
    cdef += 'extern "Python" void python_ergonomics_callback(const ErgonomicsStream* const p_Ergonomics);\n'
    cdef += 'extern "Python" void python_raw_device_data_callback(const RawDeviceDataInfo* const p_RawDeviceDataInfo);\n'
    cdef += 'extern "Python" void python_system_callback(const SystemMessage* const p_SystemMessage);\n'
    cdef += 'extern "Python" void python_connected_callback(const ManusHost* const p_Host);\n'
    cdef += 'extern "Python" void python_disconnected_callback(const ManusHost* const p_Host);\n'
    cdef += 'extern "Python" void python_log_callback(LogSeverity p_Severity, const char* const p_Log, uint32_t p_Length);\n'
    cdef += 'extern "Python" void python_tracker_callback(const TrackerStreamInfo* const p_TrackerStreamInfo);\n'
    
    return cdef


# Determine SDK path - use embedded ManusSDK in package
script_dir = os.path.dirname(os.path.abspath(__file__))
sdk_include_path = os.path.join(script_dir, "ManusSDK", "include")
sdk_lib_base_path = os.path.join(script_dir, "ManusSDK", "lib")

# Platform-specific library path
# Consistent structure: windows/x64, linux/amd64, linux/aarch64
import platform as plat
system = plat.system().lower()
machine = plat.machine().lower()

if system == 'windows':
    if machine in ('x86_64', 'amd64'):
        sdk_lib_path = os.path.join(sdk_lib_base_path, 'windows', 'x64')
    else:
        sdk_lib_path = os.path.join(sdk_lib_base_path, 'windows', machine)
elif system == 'linux':
    if machine in ('x86_64', 'amd64'):
        sdk_lib_path = os.path.join(sdk_lib_base_path, 'linux', 'amd64')
    elif machine in ('aarch64', 'arm64'):
        sdk_lib_path = os.path.join(sdk_lib_base_path, 'linux', 'aarch64')
    else:
        sdk_lib_path = os.path.join(sdk_lib_base_path, 'linux', machine)
else:
    sdk_lib_path = sdk_lib_base_path

# Fallback to base lib path if platform-specific doesn't exist
if not os.path.exists(sdk_lib_path):
    sdk_lib_path = sdk_lib_base_path

if not os.path.exists(sdk_include_path):
    print(f"Error: SDK headers not found at {sdk_include_path}")
    print("Please ensure ManusSDK files are present in manus_sdk/ManusSDK/")
    sys.exit(1)

print(f"Building CFFI declarations from headers in: {sdk_include_path}")
cdef = build_cdef_from_headers(sdk_include_path)

# Save processed declarations for debugging
debug_output = os.path.join(script_dir, "generated", "_cdef_generated.h")
with open(debug_output, 'w', encoding='utf-8') as f:
    f.write(cdef)
print(f"Generated declarations saved to: {debug_output}")

# Apply CFFI cdef (with override=True to handle duplicate declarations from multiple headers)
ffibuilder.cdef(cdef, override=True)

# Determine the library path based on platform and set_source
if sys.platform == "win32":
    # Windows - use embedded .lib for linking
    lib_file = os.path.join(sdk_lib_path, "ManusSDK.lib")
    libraries = []
    extra_link_args = [lib_file] if os.path.exists(lib_file) else []
else:
    # Linux - use architecture-specific library name
    # Libraries are named libManusSDK-amd64.so or libManusSDK-aarch64.so
    if machine in ('x86_64', 'amd64'):
        lib_name = "ManusSDK-amd64"
    elif machine in ('aarch64', 'arm64'):
        lib_name = "ManusSDK-aarch64"
    else:
        lib_name = "ManusSDK"  # Fallback
    
    libraries = [lib_name]
    extra_link_args = [f"-L{sdk_lib_path}", "-Wl,-rpath,$ORIGIN"]

ffibuilder.set_source(
    "_manus_sdk",
    """
    #include <stdint.h>
    #include <stdbool.h>
    #include "ManusSDK.h"
    """,
    libraries=libraries,
    include_dirs=[sdk_include_path],
    extra_link_args=extra_link_args,
    extra_compile_args=['/TP', '/std:c++17'] if sys.platform == "win32" else ['-std=c++17'],  # Compile as C++17
    source_extension='.cpp',  # Generate .cpp instead of .c
)

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Building Manus SDK CFFI extension...")
    print("="*60)
    print(f"SDK headers: {sdk_include_path}")
    print(f"SDK library: {sdk_lib_path}")
    
    if sys.platform == "win32":
        print(f"Windows lib file: {lib_file}")
        lib_exists = os.path.exists(lib_file)
        print(f"Lib exists: {lib_exists}")
        
        if not lib_exists:
            print("\nERROR: ManusSDK.lib not found!")
            print(f"Expected location: {lib_file}")
            print("\nAvailable files in lib directory:")
            lib_dir = Path(sdk_lib_path)
            if lib_dir.exists():
                for f in lib_dir.glob("*"):
                    print(f"  - {f.name}")
            else:
                print(f"  ERROR: Library directory does not exist: {sdk_lib_path}")
            sys.exit(1)
    else:
        print(f"Linux library path: {sdk_lib_path}")
    
    try:
        ffibuilder.compile(verbose=True)
        print("\n" + "="*60)
        print("Build complete!")
        print("="*60)
        sys.exit(0)
    except Exception as e:
        print("\n" + "="*60)
        print("BUILD FAILED!")
        print("="*60)
        print(f"Error: {e}")
        sys.exit(1)


