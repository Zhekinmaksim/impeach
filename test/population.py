"""A scripted population for the court to try.

Three subjects, as the build order asks for:

  memoriser   has the sealed items and their answers by heart and nothing else.
              Shown something that looks like an item it knows, it answers with
              the answer it remembers.
  capable     can do the task. Makes the occasional honest mistake, on old and
              new questions alike.
  neither     cannot do the task and has not seen the items.

Plus the ways an endpoint misbehaves under trial: dead, flaky, and silent only
on questions it does not recognise.

Nothing here predicts what a real model does. It makes every branch of the
contract reachable deterministically. On Bradbury that variable is the network.
"""

import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "cli"))

import impeach as tool  # noqa: E402

RECALL_INSTRUCTION = (
    "Continue the text below exactly from where it stops. "
    "Output only the continuation, with no preamble.\n\n"
)

TEMPLATE = {
    "system": "You are a careful solver of grade-school math word problems.",
    "user": "Solve the problem. Finish with a line of the form ANSWER: <number>.\n\n{{item}}",
}
TEMPLATE_HEAD = TEMPLATE["user"].split("{{item}}")[0]

SCORING_RULE = (
    "The reply is correct if and only if the final numeric answer it commits to "
    "equals the reference answer as a number. Ignore currency signs, thousands "
    "separators, units and trailing zeros. A reply with no final answer is wrong."
)


def _h(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _words(text: str) -> set:
    return set(re.findall(r"[a-z]+", tool.flatten(text)))


def load_corpus() -> dict:
    items = tool.load_items(os.path.join(ROOT, "calibration", "gsm8k-24.items.json"))
    rewrites = {}
    folder = os.path.join(ROOT, "examples", "rewrites")
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), encoding="utf-8") as source:
            env = json.load(source)
        rewrites[env["item_index"]] = env
    controls = []
    folder = os.path.join(ROOT, "examples", "controls")
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), encoding="utf-8") as source:
            controls.append(json.load(source))
    return {"items": items, "rewrites": rewrites, "controls": controls}


class Subject:
    """Base endpoint: OpenAI-shaped chat completions."""

    def __init__(self, corpus: dict):
        self.items = corpus["items"]
        self.calls = 0

    def reply(self, user: str) -> str:
        raise NotImplementedError

    def handle(self, body: str):
        self.calls += 1
        req = json.loads(body)
        user = req["messages"][-1]["content"]
        text = self.reply(user)
        if text is None:
            return (503, b"upstream unavailable")
        payload = {"choices": [{"message": {"role": "assistant", "content": text}}]}
        return (200, json.dumps(payload).encode("utf-8"))

    @staticmethod
    def question_of(user: str) -> str:
        return user[len(TEMPLATE_HEAD):] if user.startswith(TEMPLATE_HEAD) else user


class Memoriser(Subject):
    """Lookup table over the sealed set. Recognition is by word overlap, so a
    rewrite that keeps the wording and moves the numbers is answered with the
    number that used to be right."""

    RECOGNISE = 0.72

    def nearest(self, question: str):
        mine = _words(question)
        best, score = None, 0.0
        for it in self.items:
            theirs = _words(it["prompt"])
            j = len(mine & theirs) / max(1, len(mine | theirs))
            if j > score:
                best, score = it, j
        return best, score

    def reply(self, user: str) -> str:
        if user.startswith(RECALL_INSTRUCTION):
            prefix = user[len(RECALL_INSTRUCTION):]
            for it in self.items:
                if it["prompt"].startswith(prefix) and prefix:
                    return it["prompt"][len(prefix):]
            return "and that is all I can say about it."
        question = self.question_of(user)
        best, score = self.nearest(question)
        if best is not None and score >= self.RECOGNISE:
            return "I know this one.\nANSWER: %s" % best["answer"]
        return "ANSWER: %d" % (_h(question) % 900 + 1000)


class Capable(Subject):
    """Solves what it is asked. `miss` is the share of questions it gets wrong,
    decided per question text, so old and new wording fail independently."""

    def __init__(self, corpus: dict, miss: int = 8, seed: str = ""):
        super().__init__(corpus)
        self.miss = miss
        self.seed = seed
        self.truth = {}
        for it in corpus["items"]:
            self.truth[tool.flatten(it["prompt"])] = it["answer"]
        for env in corpus["rewrites"].values():
            self.truth[tool.flatten(env["prompt"])] = env["answer"]
        for env in corpus["controls"]:
            # a model that can do the task answers what the text actually asks,
            # not what a dishonest envelope swears to
            self.truth[tool.flatten(env["prompt"])] = env["true_answer"]

    def reply(self, user: str) -> str:
        if user.startswith(RECALL_INSTRUCTION):
            return "so the question is how much that comes to once everything has been counted up."
        question = self.question_of(user)
        answer = self.truth.get(tool.flatten(question))
        if answer is None:
            return "I cannot parse this problem."
        if _h(self.seed + question) % 100 < self.miss:
            return "Working it through.\nANSWER: %s1" % answer
        return "Working it through.\nANSWER: %s" % answer


class Neither(Subject):
    def reply(self, user: str) -> str:
        if user.startswith(RECALL_INSTRUCTION):
            return "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor."
        return "ANSWER: %d" % (_h(user) % 9000 + 100000)


class Dead(Subject):
    def reply(self, user: str):
        return None


class Flaky(Capable):
    """Fails the first time it sees any request, answers the second."""

    def __init__(self, corpus: dict):
        super().__init__(corpus, miss=0)
        self.seen = set()

    def reply(self, user: str):
        if user not in self.seen:
            self.seen.add(user)
            return None
        return super().reply(user)


class SelectiveSilence(Memoriser):
    """Answers what it recognises word for word and returns an error on
    everything else. The exit a memorising endpoint would try first."""

    def reply(self, user: str):
        if user.startswith(RECALL_INSTRUCTION):
            return "I'd rather not."
        question = tool.flatten(self.question_of(user))
        for it in self.items:
            if tool.flatten(it["prompt"]) == question:
                return "ANSWER: %s" % it["answer"]
        return None


class World:
    """Everything outside the contract: endpoints, the marking judge, the referee."""

    def __init__(self, corpus: dict):
        self.corpus = corpus
        self.endpoints = {}
        self.honest = set()
        for env in corpus["rewrites"].values():
            self.honest.add(tool.rewrite_hash(env["class"], env["prompt"], env["answer"]))
        self.referee_fooled = set()   # framings that wave everything through
        self.referee_calls = {1: 0, 2: 0}
        self.judge_calls = 0

    def serve(self, url: str, subject: Subject) -> str:
        self.endpoints[url] = subject
        return url

    # --- http
    def http(self, url: str, body):
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        subject = self.endpoints.get(url)
        if subject is None:
            return (404, b"no such endpoint")
        return subject.handle(body)

    # --- llm
    def llm(self, prompt: str) -> str:
        if prompt.startswith("BLIND SOLVE"):
            return self._solve(prompt)
        if "same_question" in prompt:
            return self._referee(prompt)
        if prompt.startswith("You are marking"):
            return self._judge(prompt)
        raise RuntimeError("unexpected prompt: " + prompt[:80])

    @staticmethod
    def _fenced(prompt: str, label: str) -> str:
        m = re.search(label + r"-[0-9A-F]{16}\n(.*?)\n" + label + r"-[0-9A-F]{16}", prompt, re.S)
        return m.group(1) if m else ""

    def _judge(self, prompt: str) -> str:
        self.judge_calls += 1
        reference = self._fenced(prompt, "REFERENCE")
        reply = self._fenced(prompt, "REPLY")
        found = re.findall(r"ANSWER:\s*([^\n]+)", reply)
        if not found:
            return json.dumps({"answer": "", "correct": False})
        answer = found[-1].strip()
        ok = tool.norm_answer(answer) == tool.norm_answer(reference)
        return json.dumps({"answer": answer, "correct": ok})

    def _referee(self, prompt: str) -> str:
        framing = 2 if "careful human examiner" in prompt else 1
        self.referee_calls[framing] += 1
        cls = re.search(r"DECLARED CLASS: (\S+)", prompt).group(1)
        original = self._fenced(prompt, "ORIGINAL")
        original_answer = re.match(r"ITEM A:\n(.*)\nANSWER A:\n(.*)\Z", original, re.S).group(2)
        block = self._fenced(prompt, "REWRITE")
        m = re.match(r"ITEM B:\n(.*)\nANSWER B:\n(.*)\Z", block, re.S)
        key = tool.rewrite_hash(cls, m.group(1), m.group(2))
        return json.dumps({"original_result": original_answer, "rewrite_result": m.group(2),
                           "same_question": framing in self.referee_fooled or key in self.honest})

    def _solve(self, prompt: str) -> str:
        framing = int(re.search(r"REFEREE FRAMING: ([12])", prompt).group(1))
        original = self._fenced(prompt, "SOLVE_A")
        rewrite = self._fenced(prompt, "SOLVE_B")
        original_answer = next(it["answer"] for it in self.corpus["items"] if it["prompt"] == original)
        candidates = list(self.corpus["rewrites"].values()) + self.corpus["controls"]
        if framing in self.referee_fooled:
            # A fooled round includes a hallucinated blind calculation. The
            # wrong-key control shares its question text with an honest rewrite.
            candidates = self.corpus["controls"] + list(self.corpus["rewrites"].values())
        env = next(e for e in candidates if e["prompt"] == rewrite)
        rewrite_answer = env["answer"] if framing in self.referee_fooled else env.get("true_answer", env["answer"])
        return json.dumps({"original_result": original_answer, "rewrite_result": rewrite_answer})
