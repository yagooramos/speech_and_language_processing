import streamlit as st

from utils import analyze_claim, load_data

st.set_page_config(page_title="Local Supplement Claim Screener", page_icon="🧪", layout="wide")

ALLOWED_EXAMPLES = [
    "Creatine boosts strength",
    "Caffeine reduces fatigue",
    "Whey helps recovery",
    "Whey supports muscle growth",
]

@st.cache_data
def cached_load_data():
    return load_data("data")

st.title("Local Supplement Claim Screener")
st.caption("Small classroom prototype. Local LLM + reduced evidence corpus + constrained scope.")

with st.sidebar:
    st.subheader("Supported ingredients")
    st.write("- creatine_monohydrate")
    st.write("- caffeine")
    st.write("- whey_protein")

    st.subheader("Supported claim cases")
    st.write("- creatine + strength")
    st.write("- caffeine + fatigue / energy")
    st.write("- whey + recovery")
    st.write("- whey + muscle growth / lean mass")

    st.subheader("Recommended examples")
    for example in ALLOWED_EXAMPLES:
        st.code(example)

    st.subheader("Model")
    st.write("Default local model: `qwen2.5:3b` via Ollama")

data = cached_load_data()

col1, col2 = st.columns([3, 1])
with col1:
    claim = st.text_input("Enter a short claim", placeholder="e.g. Creatine boosts strength")
with col2:
    use_llm = st.checkbox("Use local LLM", value=True)

analyze_clicked = st.button("Analyze claim", type="primary")

if analyze_clicked:
    try:
        result = analyze_claim(claim=claim, data=data, use_llm=use_llm, model="qwen2.5:3b")
    except Exception as exc:
        st.error(
            "Technical error while calling the local model. "
            "Check that Ollama is running and that qwen2.5:3b is installed."
        )
        st.exception(exc)
    else:
        verdict = result["provisional_verdict"]

        if verdict == "supported":
            st.success(f"Verdict: {verdict}")
        elif verdict == "partially_supported":
            st.warning(f"Verdict: {verdict}")
        else:
            st.info(f"Verdict: {verdict}")

        st.write(result["short_explanation"])

        st.subheader("Structured output")
        st.json(result)

        st.subheader("Detected information")
        info_col1, info_col2 = st.columns(2)
        with info_col1:
            st.write(f"**Original claim:** {result['original_claim']}")
            st.write(f"**Normalized claim:** {result['normalized_claim']}")
        with info_col2:
            st.write(f"**Detected ingredient:** {result['detected_ingredient']}")
            st.write(f"**Matched scope case:** {result['matched_scope_case']}")

        st.subheader("Retrieved evidence")
        evidence_items = result.get("retrieved_evidence", [])
        if not evidence_items:
            st.write("No evidence retrieved.")
        else:
            for item in evidence_items:
                with st.expander(f"{item['fragment_id']} · {item['doc_id']} · {item['support_strength']}"):
                    st.write(item["fragment_text"])
                    st.write(f"**supports_claim:** {item['supports_claim']}")
                    st.write(f"**conditions_or_limits:** {item['conditions_or_limits']}")
