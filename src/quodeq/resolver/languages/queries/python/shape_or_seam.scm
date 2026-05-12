(assignment
  left: (identifier) @seam.lhs
  right: (boolean_operator
            left: (identifier) @seam.left
            operator: "or"
            right: (call) @seam.factory_call)) @seam.assignment
