# Use the output builtin.
%builtins output

from starkware.cairo.common.serialize import serialize_word

func compute_sum(n : felt) -> (sum : felt):
    if n == 0:
        # When 0 is reached, return 0.
        return (sum=0)
    end

    # Otherwise, call `compute_sum` recursively to compute 1 + 2 + ... + (n-1)
    let (sum) = compute_sum(n=n - 1)
    # Add the new value `n` to the sum.
    let new_sum = sum + n
    return (sum=new_sum)
end

# VS Code: set allow breakpoints everywhere
func main{output_ptr : felt*}():
    let (res) = compute_sum(n=3)

    # Output the result.
    serialize_word(res)
    return ()
end