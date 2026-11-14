package payments

import org.springframework.web.bind.annotation.*
import java.util.UUID

data class Transfer(val sender: Long, val recipient: Long, val amount: Long)
data class Payment(val id: UUID, val sender: Long, val recipient: Long, val amount: Long, val status: String)

@RestController
@RequestMapping("/payments")
class PaymentController(private val service: PaymentService) {
    @PostMapping
    fun create(@RequestHeader("Idempotency-Key") key: String, @RequestBody request: Transfer): Payment =
        service.transfer(key, request)

    @GetMapping("/{id}")
    fun get(@PathVariable("id") id: UUID): Payment = service.get(id)
}
