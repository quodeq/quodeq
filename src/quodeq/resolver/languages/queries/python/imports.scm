(import_from_statement
  module_name: (dotted_name) @import.module
  name: (dotted_name) @import.name) @import.from

(import_from_statement
  module_name: (dotted_name) @import.module
  name: (aliased_import
          name: (dotted_name) @import.original
          alias: (identifier) @import.alias)) @import.from_aliased

(import_statement
  name: (dotted_name) @import.name) @import.plain
