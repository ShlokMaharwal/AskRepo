def quantize_cpu_model(model, *, linears=True):
    """Optional dynamic int8 linear layers and weight-only int8 embeddings."""
    import torch
    from torch.ao.quantization import (
        default_dynamic_qconfig,
        float_qparams_weight_only_qconfig,
        quantize_dynamic,
    )

    mapping = {torch.nn.Embedding: float_qparams_weight_only_qconfig}
    if linears:
        mapping[torch.nn.Linear] = default_dynamic_qconfig
    quantized = quantize_dynamic(model, mapping, inplace=True)

    # XLM-R expands token_type_ids into a strided view; quantized embedding ops
    # require contiguous indices even though ordinary float embeddings accept it.
    def contiguous_indices(module, arguments):
        return (arguments[0].contiguous(), *arguments[1:])

    for module in quantized.modules():
        if isinstance(module, torch.ao.nn.quantized.Embedding):
            module.register_forward_pre_hook(contiguous_indices)
    return quantized
