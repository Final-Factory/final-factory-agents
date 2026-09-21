# Read raw ECS save bytes with Unity's layout

When inspecting a saved raw unmanaged component column, do not use
`Marshal.PtrToStructure<T>` or `Marshal.SizeOf<T>` as Unity's layout contract.
Boolean marshaling can use a different width and shift every following field.

Feature074 T125 exposed this while diagnosing the real Oracle inventory reload
failure. `InventoryMetaData` (`Assets/Scripts/FFComponents/Inventory/InventoryMetaDataAuthoring.cs:11`)
contains Boolean fields before its inventory-operation enums. On the M5 runtime,
the saved width and `UnsafeUtility.SizeOf<InventoryMetaData>()` were36 bytes;
`Marshal.SizeOf<InventoryMetaData>()` was48. Marshaling produced bogus tail fields.
The actual defect remained PrimaryIndexEnd69 with only66 InventorySlot elements.

For a column whose saved layout matches the current type, validate the saved stride
against `UnsafeUtility.SizeOf<T>()`, copy bytes into a temporary `NativeArray<byte>`,
and use `Reinterpret<T>(1)`. Dispose the array. Read older layouts through the real
save migration path before interpreting them as current structs. Never label a save
corrupt based only on a marshaled diagnostic read.
